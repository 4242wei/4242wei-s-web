# 专家智能录入模块

专家智能录入与专家库写入分离：模型接口只生成结构化预览，只有用户在网页中确认后才调用专家库导入接口。解析失败、超时或返回无效 JSON 时不会修改专家数据。

## DeepSeek

提供商预设位于 `config/llm_providers.json`，密钥只放在本机 `.env.local`：

```dotenv
DEEPSEEK_API_KEY=
```

填入密钥后重启 `com.4242wei.web-tunnel` 即可。

DeepSeek 预设使用 V4 Flash，思考模式默认开启，思考强度默认 `low`。AI填写页可随时关闭思考模式，或在 `low / high / max` 三档间切换；模型输出始终会经过本地字段清洗和人工确认。

## 其他接口

兼容 OpenAI Chat Completions 的接口只需在 `providers` 中新增配置，设置独立的 `api_key_env`、`base_url`、`chat_path`、`model` 和 `response_path`。密钥不要写进 JSON。

例如，新增另一个兼容接口时可以复制以下提供商配置；页面会自动把它加入下拉列表：

```json
{
  "another-provider": {
    "label": "其他模型接口",
    "enabled": true,
    "adapter": "openai_compatible",
    "base_url": "https://provider.example/v1",
    "chat_path": "/chat/completions",
    "api_key_env": "ANOTHER_PROVIDER_API_KEY",
    "model": "provider-model-name",
    "json_mode": true,
    "response_path": "choices.0.message.content"
  }
}
```

非兼容接口应在 `expert_intake.py` 中实现提供商适配器，再通过 `register_provider_adapter()` 注册。专家页面和专家数据库逻辑不需要修改。
