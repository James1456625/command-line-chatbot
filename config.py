"""配置模块 - 使用 pydantic-settings 管理所有可变参数"""

from functools import lru_cache
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有可变配置集中管理，通过 .env 覆盖默认值"""

    # API 配置
    CHATBOT_API_KEY: SecretStr = Field(
        default="",
        description="大模型 API Key"
    )
    CHATBOT_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        description="API Base URL"
    )
    CHATBOT_MODEL: str = Field(
        default="deepseek-chat",
        description="模型名称"
    )

    # 对话参数
    CHATBOT_TEMPERATURE: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="生成温度，范围 [0.0, 2.0]"
    )
    CHATBOT_MAX_TOKENS: int = Field(
        default=2048,
        gt=0,
        description="最大生成 token 数"
    )
    CHATBOT_MAX_HISTORY: int = Field(
        default=20,
        gt=0,
        description="保留的最大历史消息条数"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def check_api_key(self) -> None:
        """检查 API Key 是否已配置，未配置时给出可读提示并退出"""
        if not self.CHATBOT_API_KEY.get_secret_value():
            print(
                "错误: 未配置 CHATBOT_API_KEY\n"
                "请在 .env 文件中设置，参考 .env.example\n"
                "示例: CHATBOT_API_KEY=sk-your-api-key-here"
            )
            import sys
            sys.exit(1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取配置单例，带 lru_cache 避免重复解析"""
    return Settings()
