SEED_INCIDENTS = [
    {
        "service": "checkout",
        "incident": "Checkout error rate spiked at 09:15 UTC.",
        "hypothesis": "Payment gateway timed out, triggering the circuit breaker.",
        "proposed_action": "Investigate payment-gateway health and increase timeout threshold.",
        "approved": "yes",
    },
    {
        "service": "checkout",
        "incident": "Checkout errors during peak traffic at 20:00 UTC.",
        "hypothesis": "Payment gateway latency under load caused cascading timeouts.",
        "proposed_action": "Scale payment-gateway instances during peak hours.",
        "approved": "yes",
    },
    {
        "service": "checkout",
        "incident": "Intermittent checkout failures at 11:30 UTC.",
        "hypothesis": "Payment gateway returned 502s intermittently.",
        "proposed_action": "Add retry logic with backoff for payment-gateway calls.",
        "approved": "yes",
    },
]