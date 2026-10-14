"""Run with python -m bankbot.cli; works without an API key."""
import argparse
import json
import sys
from .service import ChatService
from .dialogue import State


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="CampusBank fictional banking inquiry assistant")
    parser.add_argument("--mode", choices=["agent", "rag", "llm", "offline"], default="agent")
    parser.add_argument("--question", help="Ask one question and exit")
    parser.add_argument("--debug", action="store_true", help="Display source IDs and tool names")
    args = parser.parse_args()
    service, state = ChatService(), State()
    print("CampusBank | 中文 / English | Fictional demo / 虚构银行 | /reset, /mode offline, /quit")
    while True:
        try:
            text = args.question or input("You / 你: ")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip() in ("/quit", "quit", "exit", "退出"):
            break
        if text.strip() in ("/reset", "重置"):
            state = State()
            print("New conversation started / 已新建会话。")
            continue
        if text.startswith("/mode "):
            selected = text.split(maxsplit=1)[1].strip()
            if selected in ("agent", "rag", "llm", "offline"):
                args.mode, state = selected, State()
                print(f"Mode: {selected}; conversation reset.")
            else:
                print("Choose agent, rag, llm or offline.")
            continue
        reply = service.respond(text, state, args.mode)
        state = reply.state
        label = "客服" if reply.language == "zh" else "Assistant"
        print(f"{label} [{reply.mode}]: {reply.answer}")
        for action in getattr(reply,'actions',[]):
            print(f"{action['title']}: http://127.0.0.1:8501/?service={action['service_id']}")
        if args.debug:
            print(json.dumps({"sources": reply.source_ids, "tools": [t["name"] for t in reply.tools],
                              "language": reply.language, "latency_ms": reply.latency_ms, "usage": reply.usage, "error": reply.error}, ensure_ascii=False))
        if args.question:
            break


if __name__ == "__main__":
    main()
