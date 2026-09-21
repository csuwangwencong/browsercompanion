AGENT_CARD = {
    "name": "ReadingAgent",
    "description": "Browser page reading and grounded question answering agent.",
    "url": "http://127.0.0.1:8003/a2a",
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
    },
    "skills": [
        {"id": "page-summary", "name": "Page Summary", "description": "Summarize the current browser page."},
        {"id": "page-question-answer", "name": "Page Question Answering", "description": "Answer questions using the current page."},
        {"id": "selection-explain", "name": "Selection Explain", "description": "Explain selected text on the current page."},
        {"id": "page-search", "name": "Page Search", "description": "Find information in the current page."},
        {"id": "information-extraction", "name": "Information Extraction", "description": "Extract structured information from the current page."},
    ],
}
