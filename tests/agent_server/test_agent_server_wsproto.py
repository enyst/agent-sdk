"""Integration test to verify the agent server works with wsproto."""

import asyncio
import json
import multiprocessing
import os
import socket
import sys
import time

import pytest
import requests
import websockets


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        return s.getsockname()[1]


def run_agent_server(port, api_key, conversations_path=None, llm_profiles_dir=None):
    os.environ["OH_SESSION_API_KEYS"] = f'["{api_key}"]'
    os.environ["OH_ENABLE_VSCODE"] = "0"
    os.environ["OH_ENABLE_VNC"] = "0"
    os.environ["OH_PRELOAD_TOOLS"] = "0"
    if conversations_path is not None:
        os.environ["OH_CONVERSATIONS_PATH"] = str(conversations_path)
    if llm_profiles_dir is not None:
        os.environ["OPENHANDS_LLM_PROFILES_DIR"] = str(llm_profiles_dir)
    sys.argv = ["agent-server", "--port", str(port)]
    from openhands.agent_server.__main__ import main

    main()


@pytest.fixture(scope="session")
def agent_server():
    port = find_free_port()
    api_key = "test-wsproto-key"

    process = multiprocessing.Process(target=run_agent_server, args=(port, api_key))
    process.start()

    for _ in range(30):
        try:
            response = requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            if response.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    else:
        process.terminate()
        process.join()
        pytest.fail(f"Agent server failed to start on port {port}")

    yield {"port": port, "api_key": api_key}

    process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join()


def test_agent_server_starts_with_wsproto(agent_server):
    response = requests.get(f"http://127.0.0.1:{agent_server['port']}/docs")
    assert response.status_code == 200
    assert (
        "OpenHands Agent Server" in response.text or "swagger" in response.text.lower()
    )


@pytest.mark.asyncio
async def test_agent_server_websocket_with_wsproto(agent_server):
    port = agent_server["port"]
    api_key = agent_server["api_key"]

    response = requests.post(
        f"http://127.0.0.1:{port}/api/conversations",
        headers={"X-Session-API-Key": api_key},
        json={
            "agent": {
                "llm": {
                    "usage_id": "test-llm",
                    "model": "test-provider/test-model",
                    "api_key": "test-key",
                },
                "tools": [],
            },
            "workspace": {"working_dir": "/tmp/test-workspace"},
        },
    )
    assert response.status_code in [200, 201]
    conversation_id = response.json()["id"]

    ws_url = (
        f"ws://127.0.0.1:{port}/sockets/events/{conversation_id}"
        f"?session_api_key={api_key}&resend_all=true"
    )

    async with websockets.connect(ws_url, open_timeout=5) as ws:
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=2)
            assert response is not None
        except TimeoutError:
            pass

        await ws.send(
            json.dumps({"role": "user", "content": "Hello from wsproto test"})
        )


def _wait_for_server(port: int) -> None:
    for _ in range(30):
        try:
            response = requests.get(f"http://127.0.0.1:{port}/docs", timeout=1)
            if response.status_code == 200:
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Agent server failed to start on port {port}")


def test_agent_server_llm_switch_persists_across_restart(tmp_path):
    api_key = "test-llm-switch-key"
    conversations_path = tmp_path / "conversations"
    llm_profiles_dir = tmp_path / "llm-profiles"
    llm_profiles_dir.mkdir(parents=True, exist_ok=True)

    # Profile usage_id must not collide with the conversation's usage_id.
    (llm_profiles_dir / "alternate.json").write_text(
        json.dumps({"model": "test-provider/alternate", "usage_id": "profile-slot"}),
        encoding="utf-8",
    )

    port_1 = find_free_port()
    process_1 = multiprocessing.Process(
        target=run_agent_server,
        args=(port_1, api_key, str(conversations_path), str(llm_profiles_dir)),
    )
    process_1.start()
    try:
        _wait_for_server(port_1)
        base_1 = f"http://127.0.0.1:{port_1}"

        response = requests.post(
            f"{base_1}/api/conversations",
            headers={"X-Session-API-Key": api_key},
            json={
                "agent": {
                    "llm": {
                        "usage_id": "test-llm",
                        "model": "test-provider/test-model",
                        "api_key": "test-key",
                    },
                    "tools": [],
                },
                "workspace": {"working_dir": str(tmp_path / "workspace")},
            },
            timeout=10,
        )
        assert response.status_code in [200, 201]
        conversation_id = response.json()["id"]

        switch = requests.post(
            f"{base_1}/api/conversations/{conversation_id}/llm/switch",
            headers={"X-Session-API-Key": api_key},
            json={"profile_id": "alternate"},
            timeout=10,
        )
        assert switch.status_code == 200

        info = requests.get(
            f"{base_1}/api/conversations/{conversation_id}",
            headers={"X-Session-API-Key": api_key},
            timeout=10,
        )
        assert info.status_code == 200
        assert info.json()["agent"]["llm"]["profile_id"] == "alternate"
    finally:
        process_1.terminate()
        process_1.join(timeout=5)
        if process_1.is_alive():
            process_1.kill()
            process_1.join()

    port_2 = find_free_port()
    process_2 = multiprocessing.Process(
        target=run_agent_server,
        args=(port_2, api_key, str(conversations_path), str(llm_profiles_dir)),
    )
    process_2.start()
    try:
        _wait_for_server(port_2)
        base_2 = f"http://127.0.0.1:{port_2}"

        restored = requests.get(
            f"{base_2}/api/conversations/{conversation_id}",
            headers={"X-Session-API-Key": api_key},
            timeout=10,
        )
        assert restored.status_code == 200
        assert restored.json()["agent"]["llm"]["profile_id"] == "alternate"
    finally:
        process_2.terminate()
        process_2.join(timeout=5)
        if process_2.is_alive():
            process_2.kill()
            process_2.join()


def test_agent_server_set_llm_persists_across_restart(tmp_path):
    api_key = "test-llm-set-key"
    conversations_path = tmp_path / "conversations"

    port_1 = find_free_port()
    process_1 = multiprocessing.Process(
        target=run_agent_server, args=(port_1, api_key, str(conversations_path), None)
    )
    process_1.start()
    try:
        _wait_for_server(port_1)
        base_1 = f"http://127.0.0.1:{port_1}"

        response = requests.post(
            f"{base_1}/api/conversations",
            headers={"X-Session-API-Key": api_key},
            json={
                "agent": {
                    "llm": {
                        "usage_id": "test-llm",
                        "model": "test-provider/test-model",
                        "api_key": "test-key",
                    },
                    "tools": [],
                },
                "workspace": {"working_dir": str(tmp_path / "workspace")},
            },
            timeout=10,
        )
        assert response.status_code in [200, 201]
        conversation_id = response.json()["id"]

        update = requests.post(
            f"{base_1}/api/conversations/{conversation_id}/llm",
            headers={"X-Session-API-Key": api_key},
            json={
                "llm": {
                    "usage_id": "ignored-by-server",
                    "model": "test-provider/alternate",
                    "api_key": "test-key-2",
                }
            },
            timeout=10,
        )
        assert update.status_code == 200

        info = requests.get(
            f"{base_1}/api/conversations/{conversation_id}",
            headers={"X-Session-API-Key": api_key},
            timeout=10,
        )
        assert info.status_code == 200
        assert info.json()["agent"]["llm"]["model"] == "test-provider/alternate"
    finally:
        process_1.terminate()
        process_1.join(timeout=5)
        if process_1.is_alive():
            process_1.kill()
            process_1.join()

    port_2 = find_free_port()
    process_2 = multiprocessing.Process(
        target=run_agent_server, args=(port_2, api_key, str(conversations_path), None)
    )
    process_2.start()
    try:
        _wait_for_server(port_2)
        base_2 = f"http://127.0.0.1:{port_2}"

        restored = requests.get(
            f"{base_2}/api/conversations/{conversation_id}",
            headers={"X-Session-API-Key": api_key},
            timeout=10,
        )
        assert restored.status_code == 200
        assert restored.json()["agent"]["llm"]["model"] == "test-provider/alternate"
    finally:
        process_2.terminate()
        process_2.join(timeout=5)
        if process_2.is_alive():
            process_2.kill()
            process_2.join()
