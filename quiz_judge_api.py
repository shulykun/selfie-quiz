#!/usr/bin/env python3
"""Жюри для режима «Открытые вопросы» селфи-квиза.

POST /judge or /quiz/api/judge  {"situation": "...", "answer": "..."}
  -> {"score": int 1-10, "verdict": str, "rank": str}

DeepSeek-токен берётся из TokenStore (зашифрованная БД workspace).
Запуск: python3 quiz_judge_api.py  (порт 8003, 0.0.0.0)
"""
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
import requests

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

PORT = int(os.environ.get("QUIZ_JUDGE_PORT", "8003"))
ALLOWED_ORIGIN = os.environ.get("QUIZ_JUDGE_ORIGIN", "")
RATE_LIMIT = int(os.environ.get("QUIZ_JUDGE_RATE_LIMIT", "10"))
TRUST_PROXY = os.environ.get("QUIZ_JUDGE_TRUST_PROXY", "").lower() in {"1", "true", "yes"}
RATE_WINDOW_SECONDS = 60
_request_times = defaultdict(deque)
_rate_lock = threading.Lock()


def is_rate_limited(client_id: str) -> bool:
    """Small single-process guard; use a shared proxy limit when scaling workers."""
    now = time.monotonic()
    cutoff = now - RATE_WINDOW_SECONDS
    with _rate_lock:
        timestamps = _request_times[client_id]
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
        if len(timestamps) >= RATE_LIMIT:
            return True
        timestamps.append(now)
        return False


@app.after_request
def add_cors_headers(response):
    """Allow the local static preview without exposing the API to arbitrary sites."""
    origin = request.headers.get("Origin", "")
    local_origin = origin.startswith(("http://127.0.0.1:", "http://localhost:"))
    if local_origin or (ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


def get_deepseek_token():
    try:
        from token_store import TokenStore
        cred = TokenStore().get("deepseek")
        if isinstance(cred, dict):
            return cred.get("token") or ""
        return cred or ""
    except Exception as e:
        print(f"[judge] TokenStore error: {e}", flush=True)
        return os.environ.get("DEEPSEEK_TOKEN", "")


def judge(situation: str, answer: str) -> dict:
    token = get_deepseek_token()
    if not token:
        return {"score": 5, "verdict": "Жюри без токена — поставлено 5/10 по умолчанию.", "rank": "Без оценки"}
    prompt = (
        "Ты — жюри игры «Бой с кринжем» (cringe battle). "
        "Игроку зачитывают неловкую ситуацию, он отвечает, ЧТО КОНКРЕТНО СКАЖЕТ ИЛИ СДЕЛАЕТ. "
        "Оцени кринжовость ответа по шкале 1-10: 10 = максимально кринжово/нелепо/неловко, 1 = идеально гладко и дипломатично.\n\n"
        f"Ситуация: {situation}\n"
        f"Ответ игрока: {answer}\n\n"
        "Ответь строго JSON без пояснений: "
        '{"score": <целое 1-10>, "verdict": "<1-2 фразы вердикта с лёгкой иронией>", "rank": "<короткий ранг, напр. Король кринжа или Дипломат года>"}'
    )
    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        score = max(1, min(10, int(data.get("score", 5))))
        return {
            "score": score,
            "verdict": str(data.get("verdict", "")).strip(),
            "rank": str(data.get("rank", "")).strip(),
        }
    except Exception as e:
        print(f"[judge] API error: {e}", flush=True)
        return {"score": 5, "verdict": "Жюри задумалось и ушло в себя. Поставили 5/10.", "rank": "Без оценки"}


@app.route("/judge", methods=["POST", "OPTIONS"])
@app.route("/quiz/api/judge", methods=["POST", "OPTIONS"])
def judge_route():
    if request.method == "OPTIONS":
        return ("", 204)
    client_id = request.remote_addr or "unknown"
    if TRUST_PROXY:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            client_id = forwarded_for.split(",", 1)[0].strip() or client_id
    if is_rate_limited(client_id):
        return jsonify({"error": "rate limit exceeded"}), 429
    data = request.get_json(silent=True) or {}
    situation = str(data.get("situation", "")).strip()
    answer = str(data.get("answer", "")).strip()
    if not situation or not answer:
        return jsonify({"error": "situation and answer required"}), 400
    if len(situation) > 1000 or len(answer) > 2000:
        return jsonify({"error": "situation or answer is too long"}), 400
    result = judge(situation, answer)
    result["situation"] = situation
    result["answer"] = answer
    return jsonify(result)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"[judge] listening on 0.0.0.0:{PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=False)
