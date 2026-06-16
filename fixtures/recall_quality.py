"""Test fixtures and recall-quality probes."""

RECALL_FIXTURES = [
    {
        "name": "location_move",
        "user_id": "user-berlin",
        "session_id": "sess-berlin",
        "turns": [
            {
                "messages": [
                    {"role": "user", "content": "I just moved from NYC to Berlin for work."},
                    {"role": "assistant", "content": "Welcome to Berlin! How are you settling in?"},
                ],
                "expected_memory_keys": ["location.residence", "location.previous"],
            }
        ],
        "probes": [
            {
                "query": "Where does this user live?",
                "expected_facts": ["Berlin"],
                "optional_facts": ["NYC", "moved"],
            }
        ],
    },
    {
        "name": "employment_change",
        "user_id": "user-stripe-notion",
        "session_id": "sess-jobs",
        "turns": [
            {
                "messages": [
                    {"role": "user", "content": "I work at Stripe as a backend engineer."},
                    {"role": "assistant", "content": "Great company."},
                ],
                "expected_memory_keys": ["employment.company"],
            },
            {
                "messages": [
                    {"role": "user", "content": "Update: I just joined Notion last week."},
                    {"role": "assistant", "content": "Congrats on the new role!"},
                ],
                "expected_memory_keys": ["employment.company"],
            },
        ],
        "probes": [
            {
                "query": "Where does the user work?",
                "expected_facts": ["Notion"],
                "must_not_include": ["Stripe"],
            }
        ],
    },
    {
        "name": "preferences",
        "user_id": "user-prefs",
        "session_id": "sess-prefs",
        "turns": [
            {
                "messages": [
                    {"role": "user", "content": "I prefer dark mode and I really love typescript."},
                    {"role": "assistant", "content": "Noted."},
                ],
                "expected_memory_keys": ["preference.general", "preference.likes"],
            }
        ],
        "probes": [
            {
                "query": "What are the user's preferences?",
                "expected_facts": ["dark mode", "typescript"],
            }
        ],
    },
    {
        "name": "correction",
        "user_id": "user-correct",
        "session_id": "sess-correct",
        "turns": [
            {
                "messages": [
                    {"role": "user", "content": "I live in Paris."},
                    {"role": "assistant", "content": "Paris is lovely."},
                ],
            },
            {
                "messages": [
                    {"role": "user", "content": "Actually, I meant I live in Lyon."},
                    {"role": "assistant", "content": "Thanks for the correction."},
                ],
            },
        ],
        "probes": [
            {
                "query": "Where does the user live?",
                "expected_facts": ["Lyon"],
                "must_not_include": ["Paris"],
            }
        ],
    },
]
