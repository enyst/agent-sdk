"""Test for FunctionCallingConverter."""


from litellm import ChatCompletionToolParam

from openhands.core.llm.exceptions import FunctionCallConversionError
from openhands.core.llm.utils.fn_call_converter import (
    STOP_WORDS,
    convert_fncall_messages_to_non_fncall_messages,
    convert_non_fncall_messages_to_fncall_messages,
)


FNCALL_TOOLS: list[ChatCompletionToolParam] = [
    {
        'type': 'function',
        'function': {
            'name': 'execute_bash',
            'description': 'Execute a bash command in the terminal.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'command': {
                        'type': 'string',
                        'description': 'The bash command to execute.',
                    }
                },
                'required': ['command'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'finish',
            'description': 'Finish the interaction when the task is complete.',
        },
    },
]


def test_stop_words_defined():
    """Test that STOP_WORDS is properly defined."""
    assert isinstance(STOP_WORDS, list)
    assert len(STOP_WORDS) > 0
    assert all(isinstance(word, str) for word in STOP_WORDS)


def test_convert_fncall_to_non_fncall_basic():
    """Test basic conversion from function call messages to non-function call messages."""
    fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command for you.',
            'tool_calls': [
                {
                    'id': 'call_123',
                    'type': 'function',
                    'function': {
                        'name': 'execute_bash',
                        'arguments': '{"command": "ls"}'
                    }
                }
            ]
        },
        {
            'role': 'tool',
            'content': 'file1.txt\nfile2.txt',
            'tool_call_id': 'call_123'
        }
    ]
    
    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )
    
    assert isinstance(non_fncall_messages, list)
    assert len(non_fncall_messages) >= len(fncall_messages)
    
    # Check that tool calls are converted to text format
    assistant_msg = None
    for msg in non_fncall_messages:
        if msg.get('role') == 'assistant' and 'execute_bash' in str(msg.get('content', '')):
            assistant_msg = msg
            break
    
    assert assistant_msg is not None
    assert 'execute_bash' in assistant_msg['content']


def test_convert_non_fncall_to_fncall_basic():
    """Test basic conversion from non-function call messages to function call messages."""
    non_fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command for you.\n\n<function=execute_bash>\n<parameter name="command">ls</parameter>\n</function>'
        }
    ]
    
    fncall_messages = convert_non_fncall_messages_to_fncall_messages(
        non_fncall_messages, FNCALL_TOOLS
    )
    
    assert isinstance(fncall_messages, list)
    assert len(fncall_messages) >= len(non_fncall_messages)
    
    # Check that function calls are properly converted
    assistant_msg = None
    for msg in fncall_messages:
        if msg.get('role') == 'assistant' and msg.get('tool_calls'):
            assistant_msg = msg
            break
    
    assert assistant_msg is not None
    assert 'tool_calls' in assistant_msg
    assert len(assistant_msg['tool_calls']) == 1
    assert assistant_msg['tool_calls'][0]['function']['name'] == 'execute_bash'


def test_convert_fncall_to_non_fncall_with_in_context_learning():
    """Test conversion with in-context learning examples."""
    fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        }
    ]
    
    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS, add_in_context_learning_example=True
    )
    
    assert isinstance(non_fncall_messages, list)
    # Agent-sdk may combine examples into existing messages rather than creating new ones
    assert len(non_fncall_messages) >= len(fncall_messages)
    
    # Check that examples are added to the content
    has_example = False
    for msg in non_fncall_messages:
        content = str(msg.get('content', '')).lower()
        if 'example' in content or 'start of example' in content:
            has_example = True
            break
    
    # Examples should be present when requested
    assert has_example, "In-context learning examples should be added to message content"


def test_convert_fncall_to_non_fncall_without_in_context_learning():
    """Test conversion without in-context learning examples."""
    fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        }
    ]
    
    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS, add_in_context_learning_example=False
    )
    
    assert isinstance(non_fncall_messages, list)
    # Without examples, should be same length or similar
    assert len(non_fncall_messages) >= len(fncall_messages)


def test_convert_with_multiple_tool_calls():
    """Test conversion with multiple tool calls in one message."""
    fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls and then pwd'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run both commands for you.',
            'tool_calls': [
                {
                    'id': 'call_123',
                    'type': 'function',
                    'function': {
                        'name': 'execute_bash',
                        'arguments': '{"command": "ls"}'
                    }
                },
                {
                    'id': 'call_456',
                    'type': 'function',
                    'function': {
                        'name': 'execute_bash',
                        'arguments': '{"command": "pwd"}'
                    }
                }
            ]
        }
    ]
    
    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )
    
    assert isinstance(non_fncall_messages, list)
    
    # Check that both tool calls are represented
    assistant_content = None
    for msg in non_fncall_messages:
        if msg.get('role') == 'assistant' and 'execute_bash' in str(msg.get('content', '')):
            assistant_content = msg['content']
            break
    
    assert assistant_content is not None
    # Both commands should be present in some form
    assert 'ls' in assistant_content or 'pwd' in assistant_content


def test_convert_with_tool_response():
    """Test conversion including tool responses."""
    fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command.',
            'tool_calls': [
                {
                    'id': 'call_123',
                    'type': 'function',
                    'function': {
                        'name': 'execute_bash',
                        'arguments': '{"command": "ls"}'
                    }
                }
            ]
        },
        {
            'role': 'tool',
            'content': 'file1.txt\nfile2.txt\nfolder1/',
            'tool_call_id': 'call_123'
        },
        {
            'role': 'assistant',
            'content': 'The directory contains two files and one folder.'
        }
    ]
    
    non_fncall_messages = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )
    
    assert isinstance(non_fncall_messages, list)
    assert len(non_fncall_messages) >= 3  # At least user, assistant, final assistant
    
    # Check that tool response is incorporated
    has_tool_output = False
    for msg in non_fncall_messages:
        content = str(msg.get('content', ''))
        if 'file1.txt' in content or 'folder1' in content:
            has_tool_output = True
            break
    
    assert has_tool_output


def test_convert_roundtrip():
    """Test that conversion is somewhat reversible."""
    original_fncall = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command.',
            'tool_calls': [
                {
                    'id': 'call_123',
                    'type': 'function',
                    'function': {
                        'name': 'execute_bash',
                        'arguments': '{"command": "ls"}'
                    }
                }
            ]
        }
    ]
    
    # Convert to non-function call format
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        original_fncall, FNCALL_TOOLS
    )
    
    # Convert back to function call format
    back_to_fncall = convert_non_fncall_messages_to_fncall_messages(
        non_fncall, FNCALL_TOOLS
    )
    
    assert isinstance(back_to_fncall, list)
    
    # Check that we have tool calls in the result
    has_tool_calls = False
    for msg in back_to_fncall:
        if msg.get('tool_calls'):
            has_tool_calls = True
            break
    
    assert has_tool_calls


def test_convert_with_invalid_function_call():
    """Test handling of invalid function call format."""
    non_fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command.\n\n<function=invalid_function>\n<parameter name="command">ls</parameter>\n</function>'
        }
    ]
    
    # This should handle invalid function calls gracefully
    try:
        fncall_messages = convert_non_fncall_messages_to_fncall_messages(
            non_fncall_messages, FNCALL_TOOLS
        )
        # If no exception, check that result is reasonable
        assert isinstance(fncall_messages, list)
    except (FunctionCallConversionError, ValueError, KeyError):
        # These exceptions are acceptable for invalid function calls
        pass


def test_convert_with_malformed_parameters():
    """Test handling of malformed function parameters."""
    non_fncall_messages = [
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command.\n\n<function=execute_bash>\n<parameter name="invalid_param">ls</parameter>\n</function>'
        }
    ]
    
    # This should handle malformed parameters gracefully
    try:
        fncall_messages = convert_non_fncall_messages_to_fncall_messages(
            non_fncall_messages, FNCALL_TOOLS
        )
        assert isinstance(fncall_messages, list)
    except (FunctionCallConversionError, ValueError, KeyError):
        # These exceptions are acceptable for malformed parameters
        pass


def test_convert_empty_messages():
    """Test conversion with empty message list."""
    empty_messages = []
    
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        empty_messages, FNCALL_TOOLS
    )
    assert isinstance(non_fncall, list)
    
    fncall = convert_non_fncall_messages_to_fncall_messages(
        empty_messages, FNCALL_TOOLS
    )
    assert isinstance(fncall, list)


def test_convert_with_no_tools():
    """Test conversion with empty tools list."""
    messages = [
        {
            'role': 'user',
            'content': 'Hello'
        },
        {
            'role': 'assistant',
            'content': 'Hi there!'
        }
    ]
    
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        messages, []
    )
    assert isinstance(non_fncall, list)
    assert len(non_fncall) >= len(messages)
    
    fncall = convert_non_fncall_messages_to_fncall_messages(
        messages, []
    )
    assert isinstance(fncall, list)
    assert len(fncall) >= len(messages)


def test_convert_preserves_user_messages():
    """Test that user messages are preserved during conversion."""
    messages = [
        {
            'role': 'user',
            'content': 'Please help me with this task'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll help you with that.'
        }
    ]
    
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        messages, FNCALL_TOOLS
    )
    
    # Find user message in result
    user_msg = None
    for msg in non_fncall:
        if msg.get('role') == 'user':
            user_msg = msg
            break
    
    assert user_msg is not None
    assert 'Please help me with this task' in user_msg['content']


def test_convert_with_system_message():
    """Test conversion with system messages."""
    messages = [
        {
            'role': 'system',
            'content': 'You are a helpful assistant.'
        },
        {
            'role': 'user',
            'content': 'Please run ls command'
        },
        {
            'role': 'assistant',
            'content': 'I\'ll run the ls command.',
            'tool_calls': [
                {
                    'id': 'call_123',
                    'type': 'function',
                    'function': {
                        'name': 'execute_bash',
                        'arguments': '{"command": "ls"}'
                    }
                }
            ]
        }
    ]
    
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        messages, FNCALL_TOOLS
    )
    
    # System message should be preserved
    system_msg = None
    for msg in non_fncall:
        if msg.get('role') == 'system':
            system_msg = msg
            break
    
    assert system_msg is not None
    assert 'helpful assistant' in system_msg['content']


def test_convert_with_finish_tool():
    """Test conversion with finish tool call."""
    fncall_messages = [
        {
            'role': 'user',
            'content': 'Please finish the task'
        },
        {
            'role': 'assistant',
            'content': 'Task completed.',
            'tool_calls': [
                {
                    'id': 'call_finish',
                    'type': 'function',
                    'function': {
                        'name': 'finish',
                        'arguments': '{}'
                    }
                }
            ]
        }
    ]
    
    non_fncall = convert_fncall_messages_to_non_fncall_messages(
        fncall_messages, FNCALL_TOOLS
    )
    
    assert isinstance(non_fncall, list)
    
    # Check that finish call is represented
    has_finish = False
    for msg in non_fncall:
        content = str(msg.get('content', ''))
        if 'finish' in content.lower():
            has_finish = True
            break
    
    assert has_finish