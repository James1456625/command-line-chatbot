# 命令行对话机器人

基于 Python + OpenAI SDK 的命令行多轮对话机器人，支持流式输出。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 复制环境变量模板并填写 API Key
cp .env.example .env
# 编辑 .env，填入你的 CHATBOT_API_KEY

# 启动对话
python chatbot.py
```

## 项目结构

```
├── config.py          # pydantic-settings 配置模块
├── llm.py             # 大模型调用封装
├── chatbot.py         # 主程序入口
├── requirements.txt
├── .env.example       # 环境变量模板
├── .gitignore
└── tests/
    ├── test_config.py # 配置模块测试
    └── test_llm.py    # LLM 调用测试
```

## 运行测试

```bash
python -m pytest tests/ -v
```
