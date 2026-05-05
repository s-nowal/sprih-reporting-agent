from esg_agent.graph import agent


def test_basic_esg_report():
    result = agent.invoke({
        "messages": [{"role": "user", "content": "Generate an ESG overview report for Apple Inc."}]
    })
    assert result["messages"][-1].content
