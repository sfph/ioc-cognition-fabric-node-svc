# Semantic Negotiation Flow Example

This example demonstrates a multi-round negotiation between two agents (Alice and Bob) planning a vacation trip.

## Overview

Alice and Bob are negotiating vacation plans with conflicting preferences:
- **Alice**: Flexible on destination, prefers warm weather, $2000 budget, wants hotel with good reviews
- **Bob**: Suggests considering different accommodation types, thinks Airbnb offers better value

The negotiation explores 5 issues with multiple options each, going through rounds of proposals, rejections, and counter-offers until agreement.

## How Semantic Negotiation Works

**Available Actions:**
- **accept**: Agree to the current proposal
- **reject**: Decline the current proposal
- **counter_offer**: Propose an alternative solution

**Negotiation Flow:**
- **Round 1**: The server makes an initial proposal. All participants can only `accept` or `reject`.
- **Round 2+**: When all participants reject, the system randomly selects one participant to make a `counter_offer`.
- **After Counter-Offer**: Once a participant submits a counter-offer, the system asks other participants to `accept` or `reject` the new proposal.
- **Continue**: This cycle repeats until an agreement is reached or the maximum number of rounds is exceeded.

---

## Step 1: Start Negotiation

**What happens**: Initialize the negotiation session by providing the context, agents, and maximum negotiation rounds. The system extracts issues from the text and generates possible options for each issue.

### Request

```bash
curl -X POST http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas1/semantic-negotiation/start \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-123",
    "content_text": "Alice wants to plan a vacation trip. She is flexible on the destination but prefers somewhere warm. Her budget is limited to $2000 total.She wants to stay in a hotel with good reviews. Bob is helping her plan the trip. He suggests considering both the destination and accommodation type. He thinks an Airbnb might offer better value than a hotel.",
    "agents_raw": [
      {"id": "alice", "name": "Alice"},
      {"id": "bob", "name": "Bob"}
    ],
    "n_steps": 20
  }' | jq
```

### Response

**What you get**: The negotiation is initiated with extracted issues, possible options, and initial messages for both agents to respond to the server's initial proposal.
```json
{
  "status": "initiated",
  "session_id": "session-123",
  "round": 1,
  "n_steps": 20,

  "issues": [
    "destination",
    "somewhere warm",
    "$2000 total",
    "hotel with good reviews",
    "Airbnb"
  ],

  "options_per_issue": {
    "destination": ["Hawaii", "Florida", "Mexico", "Caribbean"],
    "somewhere warm": ["tropical climate", "desert climate", "Mediterranean climate", "subtropical climate"],
    "$2000 total": ["$1500", "$1800", "$2000", "$2200"],
    "hotel with good reviews": ["4-star hotel", "5-star hotel", "hotel with 8+ rating on review sites", "hotel with excellent customer service"],
    "Airbnb": ["entire apartment", "private room", "shared space", "luxury Airbnb"]
  },

  "messages": [
    {
      "payload": {
        "action": "respond",
        "participant_id": "alice",
        "round": 1,
        "can_counter_offer": false,
        "allowed_actions": ["accept", "reject"],
        "current_offer": {
          "destination": "Mexico",
          "somewhere warm": "tropical climate",
          "$2000 total": "$1800",
          "hotel with good reviews": "hotel with 8+ rating on review sites",
          "Airbnb": "entire apartment"
        },
        "proposer_id": "server"
      },
      "...": "other metadata fields omitted"
    },
    {
      "payload": {
        "action": "respond",
        "participant_id": "bob",
        "round": 1,
        "can_counter_offer": false,
        "allowed_actions": ["accept", "reject"],
        "current_offer": {
          "destination": "Mexico",
          "somewhere warm": "tropical climate",
          "$2000 total": "$1800",
          "hotel with good reviews": "hotel with 8+ rating on review sites",
          "Airbnb": "entire apartment"
        },
        "proposer_id": "server"
      },
      "...": "other metadata fields omitted"
    }
  ]
}
```

**Key fields**:
- `status`: "initiated" - negotiation has started
- `issues`: List of topics being negotiated
- `options_per_issue`: Possible values for each issue
- `messages`: Each agent receives a request to respond (accept/reject) to the server's initial proposal

---

## Step 2: Both Agents Consider and Reject the Offer

**What happens**: Both Alice and Bob review the initial proposal (Mexico, tropical climate, $1800, etc.), consider it carefully, but ultimately decide to reject it. The system processes their rejections and moves to the next round.

### Request

```bash
curl -X POST http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas1/semantic-negotiation/decide \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-123",
    "agent_replies": [
      {
        "participant_id": "alice",
        "action": "reject"
      },
      {
        "participant_id": "bob",
        "action": "reject"
      }
    ]
  }' | jq
```

### Response

**What you get**: Since both agents rejected, the negotiation continues to round 2. The system randomly selects Bob to make a counter-offer.
```json
{
  "status": "ongoing",
  "session_id": "session-123",
  "round": 2,
  "messages": [
    {
      "payload": {
        "action": "propose",
        "participant_id": "bob",
        "round": 2,
        "can_counter_offer": true,
        "allowed_actions": ["counter_offer"]
      },
      "...": "other metadata fields omitted"
    }
  ]
}
```

**Key fields**:
- `status`: "ongoing" - negotiation continues
- `round`: 2 - moved to next round after rejections
- `action`: "propose" - Bob is randomly selected to make a counter-offer
- `can_counter_offer`: true - Bob can propose a new offer
- `allowed_actions`: ["counter_offer"] - Only counter-offer is allowed for the selected participant

> **Note:** Only "bob" is allowed to "counter_offer" at this point.

---

## Step 3: Bob Makes a Counter-Offer

**What happens**: Bob (the randomly selected participant) submits a counter-offer, proposing an alternative - changing the destination from Mexico to Florida while keeping other terms similar. After receiving Bob's counter-offer, the system will then ask Alice to respond.

### Request

```bash
curl -X POST http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas1/semantic-negotiation/decide \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-123",
    "agent_replies": [
      {
        "participant_id": "bob",
        "action": "counter_offer",
        "offer": {
          "destination": "Florida",
          "somewhere warm": "tropical climate",
          "$2000 total": "$1800",
          "hotel with good reviews": "hotel with 8+ rating on review sites",
          "Airbnb": "entire apartment"
        }
      }
    ]
  }' | jq
```

### Response

**What you get**: Bob's counter-offer is recorded, and Alice is now asked to respond (accept or reject) to Bob's new proposal.
```json
{
  "status": "ongoing",
  "session_id": "session-123",
  "round": 2,
  "messages": [
    {
      "payload": {
        "action": "respond",
        "participant_id": "alice",
        "round": 2,
        "can_counter_offer": false,
        "allowed_actions": ["accept", "reject"],
        "current_offer": {
          "destination": "Florida",
          "somewhere warm": "tropical climate",
          "$2000 total": "$1800",
          "hotel with good reviews": "hotel with 8+ rating on review sites",
          "Airbnb": "entire apartment"
        },
        "proposer_id": "bob"
      },
      "...": "other metadata fields omitted"
    }
  ]
}
```

**Key fields**:
- `status`: "ongoing" - still negotiating
- `round`: 2 - same round
- `action`: "respond" - Alice must respond to Bob's proposal
- `current_offer`: Bob's counter-offer (Florida instead of Mexico)
- `allowed_actions`: ["accept", "reject"] - Alice can accept or reject

> **Note:** Only "alice" is allowed to "accept" or "reject" at this point.

---

## Step 4: Alice Accepts the Offer

**What happens**: Alice reviews Bob's counter-offer and decides to accept it, completing the negotiation successfully.

### Request

```bash
curl -X POST http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas1/semantic-negotiation/decide \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-123",
    "agent_replies": [
      {
        "participant_id": "alice",
        "action": "accept"
      }
    ]
  }' | jq
```

### Response

**What you get**: The negotiation concludes with an agreement. The response includes the final agreement, the complete negotiation trace with all rounds, and participant decisions.

```json
{
  "status": "agreed",
  "session_id": "session-123",
  "round": 1,
  "result": {
    "agreement": [
      {
        "issue_id": "destination",
        "chosen_option": "Florida"
      },
      {
        "issue_id": "somewhere warm",
        "chosen_option": "tropical climate"
      },
      {
        "issue_id": "$2000 total",
        "chosen_option": "$1800"
      },
      {
        "issue_id": "hotel with good reviews",
        "chosen_option": "hotel with 8+ rating on review sites"
      },
      {
        "issue_id": "Airbnb",
        "chosen_option": "entire apartment"
      }
    ],
    "timedout": false,
    "broken": false,
    "steps": 2,
    "history": [
      [
        -1,
        "server",
        [
          "Mexico",
          "tropical climate",
          "$1800",
          "hotel with 8+ rating on review sites",
          "entire apartment"
        ]
      ],
      [
        1,
        "Bob",
        [
          "Florida",
          "tropical climate",
          "$1800",
          "hotel with 8+ rating on review sites",
          "entire apartment"
        ]
      ]
    ],
    "round_decisions": {
      "1": [
        {
          "participant_id": "alice",
          "action": "reject"
        },
        {
          "participant_id": "bob",
          "action": "reject"
        }
      ],
      "2": [
        {
          "participant_id": "bob",
          "action": "counter_offer",
          "offer": {
            "destination": "Florida",
            "somewhere warm": "tropical climate",
            "$2000 total": "$1800",
            "hotel with good reviews": "hotel with 8+ rating on review sites",
            "Airbnb": "entire apartment"
          }
        },
        {
          "participant_id": "alice",
          "action": "accept"
        }
      ]
    },
    "sstp_message_trace": [
      "... (detailed message trace omitted for brevity)"
    ]
  },

  "issues": [
    "destination",
    "somewhere warm",
    "$2000 total",
    "hotel with good reviews",
    "Airbnb"
  ],

  "participant_id_by_name": {
    "Alice": "alice",
    "Bob": "bob"
  },

  "final_result": {
    "payload": {
      "status": "agreed",
      "session_id": "session-123",
      "total_rounds": 2,
      "trace": {
        "rounds": [
          {
            "round": 1,
            "proposer_id": "server",
            "offer": {
              "destination": "Mexico",
              "somewhere warm": "tropical climate",
              "$2000 total": "$1800",
              "hotel with good reviews": "hotel with 8+ rating on review sites",
              "Airbnb": "entire apartment"
            },
            "decisions": [
              { "participant_id": "alice", "action": "reject" },
              { "participant_id": "bob", "action": "reject" }
            ]
          },
          {
            "round": 2,
            "proposer_id": "bob",
            "offer": {
              "destination": "Florida",
              "somewhere warm": "tropical climate",
              "$2000 total": "$1800",
              "hotel with good reviews": "hotel with 8+ rating on review sites",
              "Airbnb": "entire apartment"
            },
            "decisions": [
              {
                "participant_id": "bob",
                "action": "counter_offer",
                "offer": {
                  "destination": "Florida",
                  "somewhere warm": "tropical climate",
                  "$2000 total": "$1800",
                  "hotel with good reviews": "hotel with 8+ rating on review sites",
                  "Airbnb": "entire apartment"
                }
              },
              { "participant_id": "alice", "action": "accept" }
            ]
          }
        ],
        "final_agreement": [
          { "issue_id": "destination", "chosen_option": "Florida" },
          { "issue_id": "somewhere warm", "chosen_option": "tropical climate" },
          { "issue_id": "$2000 total", "chosen_option": "$1800" },
          { "issue_id": "hotel with good reviews", "chosen_option": "hotel with 8+ rating on review sites" },
          { "issue_id": "Airbnb", "chosen_option": "entire apartment" }
        ],
        "timedout": false,
        "broken": false,
        "sstp_message_trace": ["... (detailed trace omitted)"]
      }
    },
    "...": "other metadata fields omitted"
  }
}
```

**Key fields**:
- `status`: "agreed" - negotiation successfully completed
- `result.agreement`: Final agreed-upon values for all issues
- `result.steps`: Total negotiation steps (2)
- `result.round_decisions`: Complete history of all participant decisions per round
  - **Round 1**: Both agents rejected server's initial proposal (Mexico)
  - **Round 2**: Bob counter-offered with Florida; Alice accepted
- `trace.rounds`: Detailed breakdown of each negotiation round with proposals and decisions
- `trace.final_agreement`: The reached agreement on all 5 issues

---

## Summary

This example demonstrates a successful 2-round negotiation:

1. **Round 1**: Server proposes Mexico vacation → Both agents reject
2. **Round 2**: Bob counter-proposes Florida vacation → Alice accepts

**Final Agreement**:
- **Destination**: Florida
- **Climate**: Tropical
- **Budget**: $1,800
- **Accommodation**: Hotel with 8+ rating
- **Type**: Entire apartment

The negotiation flow showcases:
- ✅ Issue extraction from natural language
- ✅ Multi-round negotiation with reject/counter-offer cycles
- ✅ Complete traceability of all decisions
- ✅ Successful agreement reached
