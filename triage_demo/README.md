# 门诊预问诊与智能分诊摘要 Demo

这是一个适合课程展示的 Web Demo：

- 左侧：患者与 AI 对话
- 右侧：实时生成结构化病历摘要
- 支持两种模式：
  - Mock 演示模式：无需任何模型 API，直接可以跑
  - API 模式：预留了 DeepSeek 接口位置，后续补齐 `.env` 即可

## 已实现功能

1. 聊天式预问诊界面
2. 结构化病历摘要实时更新
3. 自动提取：
   - 主诉
   - 症状持续时间
   - 伴随症状
   - 红旗征象
   - 推荐科室
   - 就诊优先级
4. 医生端摘要生成
5. 复制摘要 / 下载 JSON
6. 示例病例一键演示

## 本地运行

```bash
cd triage_demo
pip install -r requirements.txt
python app.py
```

然后打开浏览器访问：

```text
http://127.0.0.1:5000
```

## 如何切到 API 模式

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 在 `.env` 中填写你自己的模型配置：

```env
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=你的聊天补全接口地址
DEEPSEEK_MODEL=你的模型名
```

3. 页面右上角把模式切到 `API 模式`。

## 目录结构

```text
triage_demo/
├── app.py
├── requirements.txt
├── .env.example
├── README.md
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js
```

## 课程展示建议

你可以这样演示：

- 先点“腹痛案例”或“胸痛案例”
- 展示左侧对话如何触发右侧摘要更新
- 重点讲“自由文本 -> 结构化病历摘要”的转换
- 再说明后续接入 DeepSeek 后，可以把当前 Mock 规则替换为真实大模型抽取

## 可继续增强的点

1. 增加挂号入口和科室卡片
2. 支持导出 PDF 预问诊单
3. 增加年龄、既往史、过敏史字段
4. 增加医生端后台视图
5. 接入真实大模型实现更自然的追问

## 免责声明

本 Demo 仅用于课程展示与产品原型说明，不用于真实医疗诊断或急救决策。
