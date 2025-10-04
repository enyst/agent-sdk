from openhands.sdk.tool.schema import Action, Observation
from openhands.sdk.tool.tool import ToolBase


class A(Action):
    x: int


class Obs(Observation):
    def to_llm_content(self):  # type: ignore[override]
        from openhands.sdk.llm import TextContent

        return [TextContent(text="ok")]


class T(ToolBase[A, Obs]):
    @classmethod
    def create(cls, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


def test_to_responses_tool_includes_strict_and_params():
    out = T(
        name="t", description="d", action_type=A, observation_type=Obs
    ).to_responses_tool()
    assert out["type"] == "function"
    assert out["name"] == "t"
    # description is optional in the TypedDict; access via get for type safety
    assert out.get("description") in {"d", None}
    assert out["strict"] is True
    assert "parameters" in out and isinstance(out["parameters"], dict)
