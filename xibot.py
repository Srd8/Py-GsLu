import json
import os
import random
import threading
import time
from urllib import error, request

BOT_TOKEN = os.environ.get("BOT_TOKEN", "5078034194:AAGCfu2i-eWZvjcQ-1P2pjlPCuaryTo8nro").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "5220076610").strip()
STATE_FILE = os.environ.get("STATE_FILE", "stars_gifts_state.json")

# Probability of winning the single EPIC gift per spin (0.5 = 50%).
EPIC_CHANCE = 0.5

# Single EPIC gift (only one EPIC gift exists in the pool).
EPIC_GIFT = {
    "gift_id": "5170612141741595002",
    "name": "EPIC Dragon",
    "rarity": "EPIC",
}

# Standard / non-EPIC gifts pool for the multi-gift spin.
STANDARD_GIFTS = [
    {"gift_id": "5170233102089322756", "name": "Plush Toy", "rarity": "STANDARD"},
    {"gift_id": "5170250947678437525", "name": "Birthday Cake", "rarity": "STANDARD"},
    {"gift_id": "5170521118301225164", "name": "Trophy", "rarity": "STANDARD"},
    {"gift_id": "5170493347506064015", "name": "Royal Crown", "rarity": "STANDARD"},
]

STATE_LOCK = threading.Lock()


def get_spin_pool() -> list[dict]:
    return [dict(EPIC_GIFT)] + [dict(g) for g in STANDARD_GIFTS]


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"processed_charges": [], "users": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("processed_charges", [])
            data.setdefault("users", {})
            return data
    except Exception:
        return {"processed_charges": [], "users": {}}


def save_state(state: dict) -> None:
    tmp_path = f"{STATE_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)


def tg_api(method: str, payload: dict | None = None) -> dict:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing.")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error [{method}] ({e.code}): {raw}") from e


def get_available_gifts() -> dict:
    return tg_api("getAvailableGifts", {})


def build_gifts_catalog_text(tg_gifts_response: dict | None = None) -> str:
    lines = [
        "<b>الهدايا المتواجدة في السبين:</b>",
        f"- <b>{EPIC_GIFT['name']}</b> [EPIC | نسبة الحصول: <b>{EPIC_CHANCE}</b>] — <code>{EPIC_GIFT['gift_id']}</code>",
    ]
    for g in STANDARD_GIFTS:
        lines.append(f"- {g['name']} [STANDARD] — <code>{g['gift_id']}</code>")

    if tg_gifts_response and tg_gifts_response.get("ok"):
        gifts = tg_gifts_response.get("result", {}).get("gifts", [])
        if gifts:
            lines.append("")
            lines.append("<b>الهدايا المتواجدة في تيليجرام:</b>")
            for item in gifts[:15]:
                gid = item.get("id")
                sc = item.get("star_count", "?")
                lines.append(f"- <code>{gid}</code> ({sc} Stars)")
    return "\n".join(lines)


def spin_multi_gift(stars: int, rng: random.Random | None = None) -> dict:
    r = rng or random.Random()
    if r.random() < EPIC_CHANCE:
        return dict(EPIC_GIFT)
    return dict(r.choice(STANDARD_GIFTS))


def spins_count_for_stars(stars: int) -> int:
    if stars <= 0:
        return 0
    return max(1, int(stars) // 15)


def format_spin_display(spin_index: int, total_spins: int, current_item: dict, final: bool = False) -> str:
    pool_names = " | ".join(
        f"[{g['name']} (EPIC)]" if g["rarity"] == "EPIC" else g["name"]
        for g in get_spin_pool()
    )
    status_label = "النتيجة النهائية" if final else "جاري دوران السبين..."
    rarity_badge = "EPIC (نسبة 0.5)" if current_item["rarity"] == "EPIC" else "STANDARD"
    return (
        f"<b>Spin #{spin_index}/{total_spins} — {status_label}</b>\n"
        f"الهدايا المتواجدة: {pool_names}\n"
        f"الهدية المختارة: <b>{current_item['name']}</b> [{rarity_badge}]"
    )


def show_spin_in_chat(chat_id: int, spin_index: int, total_spins: int, won_gift: dict, rng: random.Random) -> None:
    pool = get_spin_pool()
    frame_1 = rng.choice(pool)
    frame_2 = rng.choice(pool)
    sent = tg_api("sendMessage", {
        "chat_id": int(chat_id),
        "text": format_spin_display(spin_index, total_spins, frame_1, final=False),
        "parse_mode": "HTML",
    })
    msg_id = sent.get("result", {}).get("message_id")
    if msg_id:
        time.sleep(0.35)
        try:
            tg_api("editMessageText", {
                "chat_id": int(chat_id),
                "message_id": int(msg_id),
                "text": format_spin_display(spin_index, total_spins, frame_2, final=False),
                "parse_mode": "HTML",
            })
        except Exception:
            pass
        time.sleep(0.35)
        try:
            tg_api("editMessageText", {
                "chat_id": int(chat_id),
                "message_id": int(msg_id),
                "text": format_spin_display(spin_index, total_spins, won_gift, final=True),
                "parse_mode": "HTML",
            })
        except Exception:
            pass


def answer_pre_checkout(pre_checkout_id: str, ok: bool = True, error_message: str = "") -> None:
    payload = {"pre_checkout_query_id": pre_checkout_id, "ok": ok}
    if not ok and error_message:
        payload["error_message"] = error_message[:200]
    tg_api("answerPreCheckoutQuery", payload)


def send_real_gift(user_id: int, gift_id: str, text: str = "") -> dict:
    payload = {
        "user_id": int(user_id),
        "gift_id": str(gift_id),
    }
    if text:
        payload["text"] = text[:128]
        payload["text_parse_mode"] = "HTML"
    return tg_api("sendGift", payload)


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload = {
        "chat_id": int(chat_id),
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_api("sendMessage", payload)


def create_star_invoice_link(title: str, description: str, payload_str: str, star_amount: int) -> str:
    res = tg_api("createInvoiceLink", {
        "title": title[:32],
        "description": description[:255],
        "payload": payload_str[:128],
        "currency": "XTR",
        "prices": [{"label": f"{star_amount} Stars", "amount": int(star_amount)}],
    })
    if not res.get("ok") or not res.get("result"):
        raise RuntimeError(f"Failed to create invoice link: {res}")
    return res["result"]


def redeem_stars_for_user(
    user_id: int,
    star_amount: int,
    charge_id: str,
    target_user_id: int | None = None,
    notify_chat_id: int | None = None,
) -> dict:
    recipient_id = int(target_user_id or user_id)
    num_spins = spins_count_for_stars(star_amount)
    rng = random.SystemRandom()

    with STATE_LOCK:
        state = load_state()
        if charge_id and charge_id in state["processed_charges"]:
            return {"status": "duplicate", "spins": []}

        user_key = str(user_id)
        user_rec = state["users"].setdefault(user_key, {
            "stars_received_total": 0,
            "gifts_sent": [],
        })
        user_rec["stars_received_total"] = int(user_rec.get("stars_received_total", 0)) + int(star_amount)

        if num_spins <= 0:
            if charge_id:
                state["processed_charges"].append(charge_id)
            save_state(state)
            return {
                "status": "insufficient_for_spin",
                "stars_received_total": user_rec["stars_received_total"],
                "spins": [],
            }

        spin_results = []
        for idx in range(num_spins):
            gift = spin_multi_gift(star_amount, rng=rng)
            if notify_chat_id:
                try:
                    show_spin_in_chat(int(notify_chat_id), idx + 1, num_spins, gift, rng)
                except Exception:
                    pass
            gift_res = send_real_gift(
                user_id=recipient_id,
                gift_id=gift["gift_id"],
                text=f"Spin #{idx + 1} ({gift['rarity']}): <b>{gift['name']}</b>",
            )
            record = {
                "gift_id": gift["gift_id"],
                "name": gift["name"],
                "rarity": gift["rarity"],
                "stars": star_amount,
                "spin_index": idx + 1,
                "recipient_id": recipient_id,
                "charge_id": charge_id,
                "gift_response": gift_res,
                "ts": int(time.time()),
            }
            user_rec["gifts_sent"].append(record)
            spin_results.append(record)

        if charge_id:
            state["processed_charges"].append(charge_id)
        save_state(state)

    return {
        "status": "sent",
        "spins": spin_results,
        "recipient_id": recipient_id,
        "stars_received_total": user_rec["stars_received_total"],
    }


def handle_callback_query(cq: dict) -> None:
    cq_id = cq.get("id")
    data = (cq.get("data") or "").strip()
    msg = cq.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    user_id = cq.get("from", {}).get("id")

    if cq_id:
        try:
            tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
        except Exception:
            pass

    if not chat_id or not user_id:
        return

    if data == "show_gifts":
        try:
            gifts_data = get_available_gifts()
        except Exception:
            gifts_data = None
        send_message(int(chat_id), build_gifts_catalog_text(gifts_data))
    elif data == "do_spin":
        rng = random.SystemRandom()
        picked = spin_multi_gift(15, rng=rng)
        show_spin_in_chat(int(chat_id), 1, 1, picked, rng)


def handle_update(update: dict) -> None:
    if not isinstance(update, dict):
        return

    if update.get("callback_query"):
        handle_callback_query(update["callback_query"])
        return

    pre_checkout = update.get("pre_checkout_query")
    if pre_checkout:
        pre_id = pre_checkout.get("id")
        currency = pre_checkout.get("currency")
        amount = int(pre_checkout.get("total_amount", 0))
        if currency == "XTR" and amount >= 1:
            answer_pre_checkout(pre_id, ok=True)
        else:
            answer_pre_checkout(
                pre_id,
                ok=False,
                error_message="يرجى إرسال نجوم صالحة بعملة XTR.",
            )
        return

    msg = update.get("message") or update.get("edited_message")
    if msg and msg.get("successful_payment"):
        sp = msg["successful_payment"]
        user_id = msg.get("from", {}).get("id")
        chat_id = msg.get("chat", {}).get("id") or user_id
        currency = sp.get("currency")
        amount = int(sp.get("total_amount", 0))
        charge_id = sp.get("telegram_payment_charge_id") or sp.get("provider_payment_charge_id") or ""
        raw_payload = sp.get("invoice_payload", "")

        recipient_id = user_id
        try:
            parsed = json.loads(raw_payload) if raw_payload else {}
            if isinstance(parsed, dict) and parsed.get("recipient_id"):
                recipient_id = int(parsed["recipient_id"])
        except Exception:
            pass

        if user_id and currency == "XTR":
            result = redeem_stars_for_user(
                user_id=int(user_id),
                star_amount=amount,
                charge_id=charge_id,
                target_user_id=int(recipient_id),
                notify_chat_id=int(chat_id),
            )
            if result.get("status") == "sent":
                lines = [
                    f"تم استلام <b>{amount}</b> نجوم وإجراء <b>Spin هدايا متعددة</b> (نسبة EPIC = <b>{EPIC_CHANCE}</b>، هدية EPIC واحدة فقط):",
                ]
                for s in result["spins"]:
                    tag = "EPIC" if s["rarity"] == "EPIC" else "STANDARD"
                    lines.append(f"- Spin #{s['spin_index']}: [{tag}] <b>{s['name']}</b>")
                lines.append(f"المستلم: <code>{recipient_id}</code>")
                send_message(int(chat_id), "\n".join(lines))
                if ADMIN_ID and str(user_id) != str(ADMIN_ID):
                    try:
                        send_message(int(ADMIN_ID), f"إشعار دفع نجوم: المستخدم <code>{user_id}</code> دفع <b>{amount}</b> نجمة.")
                    except Exception:
                        pass
        return

    if msg and isinstance(msg.get("text"), str):
        chat_id = msg.get("chat", {}).get("id")
        user_id = msg.get("from", {}).get("id")
        text = msg["text"].strip()

        if not chat_id or not user_id:
            return

        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            recipient_id = int(user_id)
            if len(parts) == 2 and parts[1].startswith("gift_to_"):
                try:
                    recipient_id = int(parts[1].replace("gift_to_", "", 1).strip())
                except ValueError:
                    recipient_id = int(user_id)

            payload_str = json.dumps({"recipient_id": recipient_id})
            link_15 = create_star_invoice_link(
                title="Multi-Gift Spin (15 Stars)",
                description="سبين هدايا متعددة مقابل 15 نجماً (هدية EPIC واحدة بنسبة 0.5)",
                payload_str=payload_str,
                star_amount=15,
            )
            link_45 = create_star_invoice_link(
                title="Multi-Gift Spin (45 Stars)",
                description="3 سبينات هدايا متعددة مقابل 45 نجماً (هدية EPIC واحدة بنسبة 0.5)",
                payload_str=payload_str,
                star_amount=45,
            )
            catalog_txt = build_gifts_catalog_text()
            send_message(
                int(chat_id),
                (
                    "<b>Spin هدايا متعددة مقابل النجوم</b>\n"
                    f"المستلم: <code>{recipient_id}</code>\n"
                    f"نسبة هدية <b>EPIC</b> (الوحيدة): <b>{EPIC_CHANCE}</b>\n\n"
                    f"{catalog_txt}\n\n"
                    "اختر الباقة أو استخدم الأزرار لعرض السبين والهدايا المتواجدة:"
                ),
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "15 نجوم -> 1 Spin", "url": link_15}],
                        [{"text": "45 نجوم -> 3 Spins", "url": link_45}],
                        [
                            {"text": "عرض Spin", "callback_data": "do_spin"},
                            {"text": "الهدايا المتواجدة", "callback_data": "show_gifts"},
                        ],
                    ]
                },
            )
        elif text == "/gifts":
            try:
                gifts_data = get_available_gifts()
            except Exception:
                gifts_data = None
            send_message(int(chat_id), build_gifts_catalog_text(gifts_data))
        elif text == "/spin":
            rng = random.SystemRandom()
            picked = spin_multi_gift(15, rng=rng)
            show_spin_in_chat(int(chat_id), 1, 1, picked, rng)


def polling_loop() -> None:
    tg_api("deleteWebhook", {"drop_pending_updates": False})
    offset = 0
    while True:
        try:
            res = tg_api("getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message", "edited_message", "callback_query", "pre_checkout_query"],
            })
            if res.get("ok"):
                for upd in res.get("result", []):
                    offset = int(upd["update_id"]) + 1
                    try:
                        handle_update(upd)
                    except Exception as err:
                        print("Update handling error:", err)
        except Exception as err:
            print("Polling error:", err)
            time.sleep(3)


def main() -> None:
    polling_loop()


if __name__ == "__main__":
    main()
