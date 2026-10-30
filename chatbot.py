"""命令行对话机器人 - 主程序

运行方式: python chatbot.py
退出方式: 输入 /quit 或 /exit
"""

from config import get_settings
from llm import call_llm


class ChatBot:
    """多轮对话机器人"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.history: list[dict] = []

    def add_message(self, role: str, content: str) -> None:
        """添加消息到历史，自动裁剪"""
        self.history.append({"role": role, "content": content})
        # 保留 system prompt，裁剪中间的历史
        max_history = self.settings.CHATBOT_MAX_HISTORY
        if len(self.history) > max_history:
            # 始终保留第一条（system prompt 如果存在），裁剪中间
            system_prompt = self.history[0] if self.history[0]["role"] == "system" else None
            if system_prompt:
                self.history = [system_prompt] + self.history[-(max_history - 1):]
            else:
                self.history = self.history[-max_history:]

    def chat(self, user_input: str) -> str:
        """发送用户消息并获取流式响应"""
        self.add_message("user", user_input)

        full_response = ""
        print("Assistant: ", end="", flush=True)

        for token in call_llm(self.history, stream=True):
            print(token, end="", flush=True)
            full_response += token

        print()  # 正常换行
        self.add_message("assistant", full_response)
        return full_response

    def reset(self) -> None:
        """清空对话历史"""
        self.history.clear()


def main() -> None:
    """主入口：启动命令行对话循环"""
    # 启动前检查 API Key
    settings = get_settings()
    settings.check_api_key()

    print("=" * 50)
    print("  命令行对话机器人 (输入 /quit 退出，/reset 重置)")
    print("=" * 50)
    print(f"  模型: {settings.CHATBOT_MODEL}")
    print(f"  温度: {settings.CHATBOT_TEMPERATURE}")
    print("=" * 50)

    bot = ChatBot()

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input in ("/quit", "/exit"):
            print("再见！")
            break
        elif user_input == "/reset":
            bot.reset()
            print("对话历史已重置。")
            continue

        bot.chat(user_input)


if __name__ == "__main__":
    main()
