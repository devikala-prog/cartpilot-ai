import os
import json
import requests
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

st.set_page_config(page_title="CartPilot AI | PayPal Agentic Commerce", page_icon="🛒", layout="wide")

# --- Mock Store Catalog ---
CATALOG = [
    {"id": "SKU-101", "name": "Keychron K2 Mechanical Keyboard", "price": 79.00, "category": "Peripherals", "desc": "Wireless 75% tactile mechanical keyboard"},
    {"id": "SKU-102", "name": "Logitech MX Master 3S Mouse", "price": 99.00, "category": "Peripherals", "desc": "Ergonomic silent wireless productivity mouse"},
    {"id": "SKU-103", "name": "Anker USB-C 7-in-1 Hub", "price": 34.00, "category": "Accessories", "desc": "4K HDMI, USB 3.0, SD card reader, 100W PD"},
    {"id": "SKU-104", "name": "DeskMat Pro Felt Pad", "price": 22.00, "category": "Accessories", "desc": "Large anti-slip wool felt desk mat"},
    {"id": "SKU-105", "name": "Sony WH-CH720N Headphones", "price": 98.00, "category": "Audio", "desc": "Lightweight noise-canceling wireless headphones"},
    {"id": "SKU-106", "name": "BenQ ScreenBar Light", "price": 109.00, "category": "Lighting", "desc": "Auto-dimming monitor light bar with zero glare"},
    {"id": "SKU-107", "name": "Aluminum Laptop Stand", "price": 29.00, "category": "Accessories", "desc": "Ergonomic ventilated riser for laptops up to 16 inch"},
]

PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com"


# --- PayPal Sandbox API Functions ---
def get_paypal_access_token() -> str:
    if "paypal_token" in st.session_state:
        return st.session_state["paypal_token"]
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_CLIENT_SECRET")
    if not client_id or not secret:
        raise ValueError("Missing PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET in .env file.")
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v1/oauth2/token",
        auth=(client_id, secret),
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    st.session_state["paypal_token"] = token
    return token


def create_paypal_order(items: list[dict], total_amount: float) -> dict:
    token = get_paypal_access_token()
    item_summary = ", ".join([f"{i['name']} (${i['price']})" for i in items])[:120]
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "description": f"CartPilot AI Bundle: {item_summary}",
                "amount": {"currency_code": "USD", "value": f"{total_amount:.2f}"},
            }
        ],
        "application_context": {
            "brand_name": "CartPilot AI Store",
            "user_action": "PAY_NOW",
            "return_url": "https://example.com",
            "cancel_url": "https://example.com",
        },
    }
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    approve_url = next((link["href"] for link in data.get("links", []) if link["rel"] == "approve"), None)
    return {"order_id": data["id"], "status": data["status"], "approve_url": approve_url, "total": total_amount, "items": items}


def capture_paypal_order(order_id: str) -> dict:
    token = get_paypal_access_token()
    resp = requests.post(
        f"{PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=10,
    )
    return resp.json()


def prepare_paypal_checkout(item_ids: list[str]) -> str:
    selected = [item for item in CATALOG if item["id"] in item_ids]
    if not selected:
        msg = f"No valid item IDs found for {item_ids}."
        st.session_state["checkout_error"] = msg
        return json.dumps({"success": False, "error": msg})
    total = sum(item["price"] for item in selected)
    try:
        order = create_paypal_order(selected, total)
        st.session_state["active_order"] = order
        st.session_state["checkout_error"] = None
        return json.dumps({"success": True, "order_id": order["order_id"], "total_usd": total, "approve_url": order["approve_url"]})
    except Exception as e:
        st.session_state["checkout_error"] = str(e)
        return json.dumps({"success": False, "error": str(e)})


# --- Groq Tool Schema ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "prepare_paypal_checkout",
            "description": "Creates a PayPal Sandbox checkout order for chosen catalog item IDs. Call ONLY when user agrees to buy or checkout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of exact catalog SKU IDs, e.g. ['SKU-101', 'SKU-104']",
                    }
                },
                "required": ["item_ids"],
            },
        },
    }
]

# --- Session State ---
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "Hi! I'm **CartPilot AI**. Tell me what you're shopping for and your budget (e.g., *'Build me a desk setup under \\$120'*), and I'll curate a bundle with an instant **PayPal Sandbox** checkout!"}
    ]
if "active_order" not in st.session_state:
    st.session_state["active_order"] = None
if "captured_receipt" not in st.session_state:
    st.session_state["captured_receipt"] = None
if "checkout_error" not in st.session_state:
    st.session_state["checkout_error"] = None

# --- Sidebar ---
with st.sidebar:
    st.header("🛍️ Store Catalog")
    for item in CATALOG:
        st.markdown(f"**{item['name']}** (`{item['id']}`) — **\\${item['price']:.2f}**  \n_{item['desc']}_")
    st.divider()
    if st.session_state["active_order"]:
        order = st.session_state["active_order"]
        st.subheader("💳 Active PayPal Order")
        st.write(f"**Order ID:** `{order['order_id']}`")
        st.write(f"**Total:** `\\${order['total']:.2f} USD`")
        st.link_button("👉 Pay Now on PayPal Sandbox", order["approve_url"], type="primary")
        if st.button("✅ Verify & Capture Payment"):
            result = capture_paypal_order(order["order_id"])
            if result.get("status") == "COMPLETED":
                st.session_state["captured_receipt"] = result
                st.success(f"Payment Captured! Transaction ID: {result['id']}")
            else:
                st.warning(f"Status: {result.get('status', 'Pending approval')}. Complete approval in PayPal first!")

# --- Main Chat UI ---
st.title("🛒 CartPilot AI — Autonomous Shopping Concierge")
st.caption("Powered by Groq Function Calling + PayPal Sandbox Orders API v2")

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if st.session_state.get("checkout_error"):
    st.error(f"PayPal API Error: {st.session_state['checkout_error']}")

if st.session_state["active_order"]:
    order = st.session_state["active_order"]
    with st.container(border=True):
        st.subheader(f"🧾 PayPal Checkout Ready — Order `{order['order_id']}`")
        st.write("**Items:** " + ", ".join([f"{i['name']} (\\${i['price']:.2f})" for i in order["items"]]))
        st.write(f"**Total Amount:** \\${order['total']:.2f} USD")
        st.link_button("💳 Complete Payment in PayPal Sandbox", order["approve_url"], type="primary")

if st.session_state["captured_receipt"]:
    receipt = st.session_state["captured_receipt"]
    st.success(f"🎉 Order `{receipt.get('id')}` Status: **{receipt.get('status')}** — Funds Captured via PayPal Sandbox!")

if prompt := st.chat_input("Ask for recommendations or say 'Checkout with PayPal'..."):
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    if "groq_model" not in st.session_state:
        chat_models = [
            m.id for m in client.models.list().data
            if "whisper" not in m.id and "guard" not in m.id and "tts" not in m.id
        ]
        preferred = ["openai/gpt-oss-120b", "qwen/qwen3-32b", "llama-3.1-8b-instant", "openai/gpt-oss-20b"]
        st.session_state["groq_model"] = next((m for m in preferred if m in chat_models), chat_models[0])

    active_model = st.session_state["groq_model"]

    system_prompt = f"""
    You are CartPilot AI, an autonomous shopping concierge connected to PayPal Sandbox.
    Available Catalog (JSON): {json.dumps(CATALOG)}
    Rules:
    1. Recommend products strictly from the catalog that fit the user's needs and budget. Show exact prices and math.
    2. When the user confirms they want to buy or checkout (e.g., says "yes", "checkout", "buy"), call `prepare_paypal_checkout` with the exact list of `item_ids`.
    3. Only say the order was created if `prepare_paypal_checkout` returns `"success": true`. If it returns an error, report the error clearly.
    """

    api_messages = [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": m["content"].replace(r"\$", "$")} for m in st.session_state["messages"]
    ]

    with st.chat_message("assistant"):
        with st.spinner(f"CartPilot is thinking ({active_model})..."):
            try:
                response = client.chat.completions.create(
                    model=active_model,
                    messages=api_messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.3,
                )
                choice_msg = response.choices[0].message

                if choice_msg.tool_calls:
                    api_messages.append({
                        "role": "assistant",
                        "content": choice_msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in choice_msg.tool_calls
                        ],
                    })
                    for tc in choice_msg.tool_calls:
                        args = json.loads(tc.function.arguments)
                        tool_result = prepare_paypal_checkout(args.get("item_ids", []))
                        api_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_result,
                        })
                    followup = client.chat.completions.create(
                        model=active_model,
                        messages=api_messages,
                        temperature=0.3,
                    )
                    raw_reply = followup.choices[0].message.content
                else:
                    raw_reply = choice_msg.content

                clean_reply = (raw_reply or "Order created! Click the payment button below.").replace("$", r"\$")
                st.markdown(clean_reply)
                st.session_state["messages"].append({"role": "assistant", "content": clean_reply})
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")