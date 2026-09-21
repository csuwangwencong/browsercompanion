# BrowserCompanion — 网易云音乐 AI 伴随式控制方案

---

## 一、整体架构

BrowserCompanion 采用 **Chrome Extension + 主 Agent + 多垂域 Agent + Browser Execution Broker** 的分层架构。

核心原则：

1. **Chrome Extension 不承载 AI 业务决策**，但 Background Service Worker 不再只是薄 HTTP 代理，而是浏览器侧的 **Browser Gateway**，负责浏览器连接、标签页路由、Content Script 生命周期和执行结果回传。
2. **主 Agent 是智能编排中枢**，负责用户意图路由、Agent Registry、A2A 调度、会话管理，以及 Browser Execution Broker。
3. **垂域 Agent 通过 A2A 与主 Agent 通信**。当前实现 Music Agent，后续可以扩展 Video Agent、Search Agent、Shopping Agent 等。
4. **垂域 Agent 不直接连接 Content Script**。垂域 Agent 生成并校验领域 Action 后，通过主 Agent 的 Browser Execution Broker 发起浏览器执行请求。
5. **Content Script 只做确定性执行**，并通过 Site Adapter 屏蔽具体网站 DOM / HTMLMediaElement 差异。
6. **LLM 输出一律视为不可信结构化输入**，必须经过 Schema Validation、confidence policy 和执行上下文校验后才能进入 Browser Gateway。

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Chrome Extension                                                           │
│                                                                            │
│  ┌──────────────┐     chrome.runtime      ┌──────────────────────────────┐ │
│  │ Side Panel   │ ◀────────────────────▶ │ Background Service Worker    │ │
│  │ Chat UI      │                        │ Browser Gateway              │ │
│  └──────────────┘                        │ - Browser Session            │ │
│                                          │ - Tab / Frame Routing        │ │
│                                          │ - Request Correlation        │ │
│                                          │ - Agent Connection           │ │
│                                          └──────────────┬───────────────┘ │
│                                                         │                  │
│                                           chrome.tabs.sendMessage          │
│                                                         │                  │
│                                                         ▼                  │
│                                          ┌──────────────────────────────┐ │
│                                          │ Content Script               │ │
│                                          │   └─ NeteasePlayerAdapter    │ │
│                                          │      HTMLMediaElement / DOM  │ │
│                                          └──────────────────────────────┘ │
└───────────────────────────────────────────────┬────────────────────────────┘
                                                │
                              HTTP/SSE + WebSocket
                                                │
                                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 主 Agent（Python FastAPI，localhost:8001）                                 │
│                                                                            │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐   │
│  │ Intent Router│  │ Agent Registry  │  │ Browser Execution Broker    │   │
│  │ / Orchestrator│ │ + A2A Client    │  │ - Context Registry          │   │
│  └──────────────┘  └────────┬────────┘  │ - WS Session Routing        │   │
│                             │           │ - Action Policy             │   │
│                             │           └─────────────────────────────┘   │
└─────────────────────────────┼──────────────────────────────────────────────┘
                              │ A2A Protocol
                              │ JSON-RPC over HTTP
              ┌───────────────┼──────────────────────┐
              │               │                      │
              ▼               ▼                      ▼
┌──────────────────┐ ┌──────────────────┐  ┌──────────────────┐
│ Music Agent      │ │ Video Agent      │  │ Other Agents ... │
│ localhost:8000   │ │ future           │  │ future           │
│ - Ollama         │ │                  │  │                  │
│ - Action Schema  │ │                  │  │                  │
│ - Domain Policy  │ │                  │  │                  │
└─────────┬────────┘ └──────────────────┘  └──────────────────┘
          │
          │ HTTP Browser Execution Request
          │ （基础设施 RPC，不是 A2A）
          ▼
   Main Agent Browser Execution Broker
```

### 1.1 为什么主 Agent 与垂域 Agent 使用 A2A

后续系统会扩展多个垂域 Agent，因此主 Agent 不应该硬编码 Music Agent 的具体实现，而应该通过 Agent Card / skills 完成能力发现与路由。

预期结构：

```text
Main Agent
 ├── A2A → Music Agent
 ├── A2A → Video Agent
 ├── A2A → Search Agent
 ├── A2A → Shopping Agent
 └── A2A → ...
```

A2A 负责的是 **Agent 之间的任务语义和生命周期**；Browser Execution Broker 负责的是 **浏览器基础设施执行 RPC**。两者职责必须分开。

### 1.2 为什么垂域 Agent 不直接连接 Content Script

Content Script 属于 Chrome Extension 的执行环境。浏览器标签页、frame、页面生命周期和权限都应该由 Extension Background 统一管理。

因此禁止：

```text
Music Agent ──WebSocket──▶ Content Script
```

改为：

```text
Music Agent
    │
    │ Browser Execution Request
    ▼
Main Agent / Browser Execution Broker
    │
    │ WebSocket
    ▼
Extension Background / Browser Gateway
    │
    │ chrome.tabs.sendMessage
    ▼
Content Script
    │
    ▼
NeteasePlayerAdapter
```

这样可以统一解决多标签页路由、多个垂域 Agent 共享浏览器执行能力、连接鉴权和执行结果关联问题。

---

## 二、通信链路

系统共有五类主要通信链路：

| # | 链路 | 协议 | 说明 |
|---|------|------|------|
| 1 | Side Panel ↔ Background Browser Gateway | `chrome.runtime.sendMessage` | 插件 UI 与浏览器网关通信 |
| 2 | Background ↔ 主 Agent `/chat` | HTTP POST + SSE | 用户请求与流式状态/回复 |
| 3 | Background Browser Gateway ↔ 主 Agent Browser Broker | WebSocket | 主 Agent 主动向浏览器发送 EXECUTE；Background 回传 RESULT / 状态 |
| 4 | 主 Agent ↔ 垂域 Agent | A2A JSON-RPC over HTTP | Agent 任务调度、状态和结果 |
| 5 | Background ↔ Content Script | `chrome.tabs.sendMessage` / `chrome.runtime` | 精确路由到 tab/frame 执行动作 |

> 注意：Browser Execution Request 是垂域 Agent 到主 Agent Browser Broker 的基础设施 RPC，不属于 A2A。A2A 仍然只用于 Agent 任务通信。

---

## 三、组件职责

| 组件 | 技术栈 | 角色 | 职责 |
|------|--------|------|------|
| **Side Panel** | HTML/CSS/JS | UI | 输入、消息展示、任务状态展示、错误提示 |
| **Background Browser Gateway** | Chrome MV3 Service Worker | 浏览器网关 | 主 Agent 连接、browser session、tab/frame 路由、Content Script 消息转发、requestId 关联 |
| **Content Script** | JS | 页面执行入口 | 接收 Browser Gateway 指令、调用 Site Adapter、回传结果 |
| **NeteasePlayerAdapter** | JS | 网站适配器 | 网易云页面探测、HTMLMediaElement / DOM 控制、能力查询 |
| **主 Agent** | Python FastAPI | 编排中枢 | 意图路由、Agent Registry、A2A 调度、SSE 输出、Browser Execution Broker |
| **MiMo API** | 云服务 | 主 Agent LLM | 通用对话、复杂意图路由；成功控制回复优先模板化 |
| **Music Agent** | Python FastAPI | 音乐垂域 Agent | A2A Server、Ollama 解析、Action Schema、confidence policy、调用 Browser Execution Broker |
| **Ollama / qwen2.5:7b-instruct** | 本地服务 | 音乐领域 LLM | 自然语言 → 结构化 Music Action |
| **Browser Execution Broker** | 主 Agent 内部模块 | 执行基础设施 | execution context、WebSocket session、action policy、请求/结果相关性 |

### 3.1 逻辑架构与物理部署分离

逻辑上 Music Agent 是独立垂域 Agent，必须保持 A2A 边界。

MVP 可以独立运行在 `localhost:8000`，主 Agent 运行在 `localhost:8001`。后续其他 Agent 可以独立端口或独立机器部署，主 Agent 通过 Agent Registry 管理。

---

## 四、统一标识与执行上下文

为解决多标签页、多浏览器会话和并发 Action，系统引入以下标识：

| 标识 | 生成方 | 生命周期 | 用途 |
|------|--------|----------|------|
| `sessionId` | Side Panel / 主 Agent | 对话会话 | 对话上下文 |
| `browserSessionId` | Background | Extension WebSocket 会话 | 标识当前浏览器网关实例 |
| `tabId` | Chrome | 标签页生命周期 | 精确目标 Tab |
| `frameId` | Chrome | Frame 生命周期 | 精确目标 Frame |
| `executionContextId` | 主 Agent | 单次/短期任务 | 给垂域 Agent 的不透明执行上下文 |
| `taskId` | A2A | Agent Task 生命周期 | A2A 任务 |
| `requestId` | Browser Broker | 单次执行请求 | Browser EXECUTE / RESULT 关联 |

### 4.1 executionContextId

主 Agent 收到用户请求后，根据 Background 提供的浏览器上下文创建：

```json
{
  "executionContextId": "ctx-8f...",
  "browserSessionId": "browser-a1...",
  "tabId": 123,
  "frameId": 0,
  "url": "https://music.163.com/st/webplayer",
  "capabilities": ["music.play", "music.pause", "music.set_volume"]
}
```

垂域 Agent **只拿到 `executionContextId`**，不直接控制或随意指定 tabId。

这样可以避免垂域 Agent 将动作发到错误页面，也便于主 Agent统一做权限和 capability 校验。

---

## 五、统一 Action 模型

多个垂域 Agent 存在同名动作，例如 `play`、`search`、`open`，因此 Action 必须带 namespace。

推荐格式：

```json
{
  "namespace": "music",
  "name": "set_volume",
  "params": {
    "value": 0.5
  }
}
```

动作命名示例：

```text
music.play
music.pause
music.toggle_play
music.set_volume
music.set_playback_rate
music.seek
music.next_track
music.previous_track
music.get_status
music.get_song_info

video.play                 # future
video.pause                # future
browser.open_url           # future
browser.scroll             # future
```

### 5.1 Music Action Schema

Music Agent 对 Ollama 输出使用 Pydantic 严格校验。

```python
from typing import Literal, Union
from pydantic import BaseModel, Field

class PlayParams(BaseModel):
    pass

class VolumeParams(BaseModel):
    value: float = Field(ge=0.0, le=1.0)

class RateParams(BaseModel):
    value: Literal[0.5, 1.0, 1.5, 2.0]

class SeekParams(BaseModel):
    offset: float = Field(ge=-600, le=600)

class MusicAction(BaseModel):
    namespace: Literal["music"] = "music"
    name: Literal[
        "play", "pause", "toggle_play", "set_volume",
        "set_playback_rate", "seek", "next_track",
        "previous_track", "get_status", "get_song_info"
    ]
    params: dict = {}
    confidence: float = Field(ge=0.0, le=1.0)
```

实际实现中可以进一步使用 discriminated union，让不同 Action 绑定不同 Params Schema。

### 5.2 Action 执行安全链

```text
LLM Output
    ↓
JSON Parse
    ↓
Action Schema Validation
    ↓
Confidence Policy
    ↓
Execution Context / Capability Validation
    ↓
Browser Execution Broker
    ↓
Browser Gateway
    ↓
Site Adapter
```

任何一层失败都不得进入下一层。

---

## 六、confidence 策略

`confidence` 不只是 telemetry，而是执行策略的一部分。

默认策略：

| confidence | 策略 |
|------------|------|
| `>= 0.85` | Schema / Context 校验通过后直接执行 |
| `0.60 ~ 0.85` | 增加规则校验、页面 capability 校验；通过后执行 |
| `< 0.60` | 不执行，A2A 返回 `input-required` 或失败，由主 Agent 请求用户澄清 |

示例：

```python
if action.confidence < 0.60:
    return input_required("无法确定你想执行的音乐操作")

validate_schema(action)
validate_execution_context(context_id, action)

if action.confidence < 0.85:
    run_domain_rules(action)

return await browser_executor.execute(...)
```

> confidence 永远不能绕过 Schema Validation。即使 confidence=0.99，非法参数也必须拒绝。

---

## 七、A2A Task 生命周期

A2A Task 状态统一表示 **用户领域任务是否真正完成**，不能只表示“Agent 已经生成 Action”。

支持状态：

```text
submitted
   ↓
working
   ├───────────────┐
   ↓               ↓
completed         failed
   │
   └─ input-required（需要补充用户输入时可进入）
```

### 7.1 状态语义

| 状态 | 语义 |
|------|------|
| `submitted` | A2A Task 已接收 |
| `working` | 正在解析、校验或执行 |
| `input-required` | 低 confidence / 缺少必要参数，需要用户补充信息 |
| `completed` | Action 已在目标浏览器页面执行成功 |
| `failed` | 解析、Schema、上下文、Browser Gateway 或页面执行任一阶段失败 |
| `canceled` | 任务被取消 |

### 7.2 禁止的状态组合

不再允许：

```text
Task.state = completed
artifact.success = false
```

应改为：

```text
Browser RESULT.success = false
        ↓
Task.state = failed
```

这样主 Agent 只需要依赖 Task state 判断领域任务最终结果。

---

## 八、数据流详解

### 8.1 音乐控制流程："把音量调到 50%"

```text
步骤  组件                           动作
────────────────────────────────────────────────────────────────────────────
 1    用户                           Side Panel 输入“把音量调到50%”

 2    Side Panel                     → Background
                                     USER_MESSAGE + sessionId

 3    Background Browser Gateway     获取当前 active tab / frame / URL
                                     → POST http://localhost:8001/chat
                                     携带 browser context

 4    主 Agent                       创建 executionContextId
                                     保存 contextId → browserSession/tab/frame 映射

 5    主 Agent                       Intent Router 判断 music_control

 6    主 Agent                       A2A tasks/send → Music Agent
                                     TextPart: 用户原始输入
                                     DataPart: executionContextId

 7    Music Agent                    Task: submitted → working
                                     调用 Ollama 解析自然语言

 8    Ollama                         返回结构化结果
                                     music.set_volume(value=0.5)
                                     confidence=0.92

 9    Music Agent                    Schema Validation
                                     confidence policy

10    Music Agent                    POST Main Agent /internal/browser/execute
                                     {
                                       contextId,
                                       action:{namespace:"music", ...}
                                     }

11    Main Agent Browser Broker      解析 contextId
                                     校验 browser session / tab / capability
                                     生成 requestId

12    Main Agent                     WebSocket → Background Browser Gateway
                                     EXECUTE(requestId, tabId, frameId, action)

13    Background Browser Gateway     chrome.tabs.sendMessage(tabId, ...)
                                     精确发送给 Content Script

14    Content Script                 将 action 交给 NeteasePlayerAdapter

15    NeteasePlayerAdapter           audio.volume = 0.5
                                     再读取实际 audio.volume 作为结果

16    Content Script                 RESULT → Background

17    Background                     WebSocket RESULT → Main Agent Browser Broker

18    Main Agent Broker              requestId 对应 Future 完成
                                     HTTP 返回 Music Agent

19    Music Agent                    Browser result success=true
                                     A2A Task → completed
                                     artifact 携带执行结果

20    主 Agent                       收到 A2A completed
                                     使用确定性模板生成回复
                                     “已将音量调至 50%”

21    主 Agent                       SSE → Background
                                     result + done

22    Background                     → Side Panel

23    Side Panel                     显示最终结果
```

### 8.2 为什么成功控制回复不再默认调用 MiMo

以下结果：

```json
{
  "action": "music.set_volume",
  "success": true,
  "data": {"volume": 0.5}
}
```

可以确定性生成：

```text
已将音量调至 50%
```

无需再调用一次云端 LLM。

只有复杂结果、多步骤任务或需要自然语言总结时，主 Agent 才调用 MiMo 生成最终回复。

### 8.3 通用对话流程

```text
用户
 ↓
Side Panel
 ↓
Background
 ↓
POST /chat
 ↓
Main Agent
 ↓
Intent Router → general
 ↓
MiMo Streaming
 ↓
SSE
 ↓
Side Panel
```

### 8.4 低 confidence 流程

```text
用户：“弄一下声音”
 ↓
Music Agent
 ↓
confidence = 0.42
 ↓
Task = input-required
 ↓
Main Agent
 ↓
“你希望调高、调低，还是设置到某个具体音量？”
```

### 8.5 Browser 执行失败流程

```text
Music Agent
 ↓
Browser Broker
 ↓
Background
 ↓
Content Script
 ↓
NeteasePlayerAdapter: audio element not found
 ↓
RESULT.success=false
 ↓
Music Agent
 ↓
A2A Task.state=failed
 ↓
Main Agent
 ↓
Side Panel 显示错误和建议
```

---

## 九、Browser Gateway 设计

### 9.1 Background 不承担 AI 业务逻辑

Background 虽然从“薄代理”升级为 Browser Gateway，但仍不做：

- 自然语言理解
- Agent 路由决策
- Music Action 语义推理
- LLM 调用

Background 只负责浏览器基础设施：

- 与主 Agent 建立 WebSocket
- browserSession 注册
- tab/frame 路由
- Content Script 探测
- EXECUTE / RESULT 转发
- requestId 关联
- 重连和心跳

### 9.2 Browser Gateway 注册

Background 启动后连接：

```text
ws://127.0.0.1:8001/browser/ws
```

注册消息：

```json
{
  "type": "REGISTER",
  "protocolVersion": "1.0",
  "browserSessionId": "browser-uuid",
  "extensionVersion": "1.1.0"
}
```

主 Agent 返回：

```json
{
  "type": "REGISTERED",
  "browserSessionId": "browser-uuid"
}
```

### 9.3 页面能力注册

Background 可通过 Content Script 查询当前页面：

```json
{
  "type": "CAPABILITY_REPORT",
  "tabId": 123,
  "frameId": 0,
  "url": "https://music.163.com/st/webplayer",
  "adapter": "netease",
  "capabilities": [
    "music.play",
    "music.pause",
    "music.set_volume",
    "music.seek",
    "music.next_track",
    "music.previous_track",
    "music.get_status",
    "music.get_song_info"
  ]
}
```

### 9.4 EXECUTE 协议

主 Agent → Background：

```json
{
  "type": "EXECUTE",
  "requestId": "req-001",
  "target": {
    "tabId": 123,
    "frameId": 0
  },
  "action": {
    "namespace": "music",
    "name": "set_volume",
    "params": {"value": 0.5}
  }
}
```

Background → Content Script：

```javascript
chrome.tabs.sendMessage(
  123,
  {
    type: 'EXECUTE',
    requestId: 'req-001',
    action: {
      namespace: 'music',
      name: 'set_volume',
      params: { value: 0.5 }
    }
  },
  { frameId: 0 }
);
```

Content Script 返回：

```json
{
  "type": "RESULT",
  "requestId": "req-001",
  "success": true,
  "data": {"volume": 0.5}
}
```

Background 将 RESULT 通过 WebSocket 原样回传主 Agent。

### 9.5 多标签页处理

不再广播动作给所有网易云标签页。

所有执行请求必须有精确目标：

```text
browserSessionId
       +
tabId
       +
frameId
```

如果目标 Tab 已关闭，Browser Gateway 立即返回：

```json
{
  "success": false,
  "error": {
    "code": "TARGET_TAB_NOT_FOUND",
    "message": "目标标签页已关闭"
  }
}
```

---

## 十、Content Script 与 Site Adapter

### 10.1 Content Script 职责

Content Script 只负责：

1. 接收 Background 的执行请求
2. 根据 namespace / adapter 调用对应 Site Adapter
3. 捕获异常
4. 回传结构化结果

建议目录：

```text
extension/content/
├── bridge.js
└── adapters/
    └── netease-player.js
```

### 10.2 NeteasePlayerAdapter

```javascript
class NeteasePlayerAdapter {
  async execute(action) {
    switch (action.name) {
      case 'play':
        return this.play();
      case 'pause':
        return this.pause();
      case 'set_volume':
        return this.setVolume(action.params.value);
      case 'set_playback_rate':
        return this.setPlaybackRate(action.params.value);
      case 'seek':
        return this.seek(action.params.offset);
      case 'next_track':
        return this.nextTrack();
      case 'previous_track':
        return this.previousTrack();
      case 'get_status':
        return this.getStatus();
      case 'get_song_info':
        return this.getSongInfo();
      default:
        throw new Error(`Unsupported music action: ${action.name}`);
    }
  }
}
```

### 10.3 获取播放器策略

播放器获取不再假定一定能得到 `<audio>`，而采用能力探测：

```text
HTMLMediaElement Adapter
        ↓ fallback
DOM Control Adapter
        ↓ fallback
Site-specific Strategy
```

对当前网易云实现：

1. 当前 document 查询 `<audio>`
2. 可访问的同源 iframe 中查询
3. MutationObserver 等待动态创建
4. 如果仍失败，部分动作尝试 DOM 控件方式
5. 返回 capability 降级状态

### 10.4 参数再次防御性校验

即使 Agent 已经做过 Schema Validation，执行端仍需防御性 clamp：

```javascript
setVolume(value) {
  const safeValue = Math.max(0, Math.min(1, Number(value)));
  const audio = this.requireAudio();
  audio.volume = safeValue;
  return { volume: audio.volume };
}
```

执行成功后返回 **实际读取值**，不要简单回显输入参数。

---

## 十一、主 Agent 设计

### 11.1 主要模块

```text
main_agent/
├── main.py
├── chat.py
├── config.py
├── intent/
│   ├── router.py
│   └── prompts.py
├── agents/
│   ├── registry.py
│   └── a2a_client.py
├── browser/
│   ├── ws_router.py
│   ├── session_manager.py
│   ├── context_registry.py
│   ├── execution_broker.py
│   └── models.py
├── reply/
│   ├── renderer.py
│   └── llm_reply.py
└── mimo_api.py
```

### 11.2 `/chat` 请求

Background 发送：

```json
{
  "message": "把音量调到50%",
  "sessionId": "chat-001",
  "browser": {
    "browserSessionId": "browser-001",
    "tabId": 123,
    "frameId": 0,
    "url": "https://music.163.com/st/webplayer"
  }
}
```

主 Agent 创建 executionContextId 后，调用 Music Agent。

### 11.3 SSE Event 规范

由于本地 Ollama 可能推理较慢，UI 不能在 30~60 秒内没有反馈。

SSE 不只输出文本，还输出状态事件：

```text
event: status
data: {"state":"routing"}

event: status
data: {"state":"thinking","agent":"music"}

event: status
data: {"state":"executing"}

event: result
data: {"text":"已将音量调至 50%"}

event: done
data: {}
```

Side Panel 可展示：

```text
正在识别音乐控制指令…
正在执行…
已将音量调至 50%
```

### 11.4 确定性 Reply Renderer

简单控制结果不再默认调用 MiMo：

```python
def render_music_result(action: dict, data: dict) -> str:
    name = action["name"]

    if name == "set_volume":
        return f"已将音量调至 {round(data['volume'] * 100)}%"
    if name == "pause":
        return "已暂停播放"
    if name == "play":
        return "已开始播放"
    if name == "next_track":
        return "已切换到下一首"

    return "操作已完成"
```

复杂任务再调用 MiMo。

---

## 十二、Browser Execution Broker

### 12.1 内部调用接口

Music Agent 调用：

```text
POST http://127.0.0.1:8001/internal/browser/execute
```

请求：

```json
{
  "agent": "music",
  "taskId": "task-001",
  "executionContextId": "ctx-001",
  "action": {
    "namespace": "music",
    "name": "set_volume",
    "params": {"value": 0.5}
  }
}
```

主 Agent Broker：

1. 验证调用方 Agent
2. 查找 executionContextId
3. 验证 namespace 与 Agent 权限
4. 验证目标 browserSession / tab 存活
5. 验证 capability
6. 生成 requestId
7. WebSocket 发送 EXECUTE
8. 等待 RESULT
9. 返回垂域 Agent

### 12.2 Broker 结果

成功：

```json
{
  "requestId": "req-001",
  "success": true,
  "data": {"volume": 0.5}
}
```

失败：

```json
{
  "requestId": "req-001",
  "success": false,
  "error": {
    "code": "AUDIO_NOT_FOUND",
    "message": "未找到可控制的播放器"
  }
}
```

---

## 十三、Music Agent 设计

### 13.1 Agent Card

```python
AGENT_CARD = {
    "name": "MusicControllerAgent",
    "description": "音乐控制垂域 Agent：将自然语言解析为结构化音乐动作，并通过 Browser Execution Broker 执行",
    "url": "http://127.0.0.1:8000/a2a",
    "version": "1.1.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": True
    },
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [{
        "id": "music-control",
        "name": "Music Player Control",
        "description": "播放、暂停、音量、播放速率、进度、切歌、状态和歌曲信息",
        "tags": ["music", "player", "browser"],
        "examples": [
            "暂停音乐",
            "把音量调到50%",
            "快进30秒",
            "现在在放什么歌",
            "切到下一首",
            "1.5倍速播放"
        ]
    }]
}
```

### 13.2 A2A 输入

主 Agent 发送：

```json
{
  "jsonrpc": "2.0",
  "id": "rpc-001",
  "method": "tasks/send",
  "params": {
    "id": "task-001",
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "把音量调到50%"
        },
        {
          "type": "data",
          "data": {
            "executionContextId": "ctx-001"
          }
        }
      ]
    }
  }
}
```

### 13.3 Music Agent 核心流程

```text
A2A Task submitted
      ↓
working
      ↓
Ollama parse
      ↓
Schema Validation
      ↓
confidence policy
      ↓
Browser Execution Broker
      ↓
Browser result
   ┌─────────────┐
 success       failure
   ↓             ↓
completed      failed
```

### 13.4 Ollama Prompt 输出

```json
{
  "namespace": "music",
  "name": "set_volume",
  "params": {
    "value": 0.5
  },
  "confidence": 0.92
}
```

如果 JSON 无法解析，不再默认 fallback 为 `get_status`，因为这可能产生与用户意图不一致的执行。

应返回解析失败或低 confidence：

```json
{
  "error": "ACTION_PARSE_FAILED"
}
```

---

## 十四、Timeout 设计

本地 Ollama 推理在 CPU、首次模型加载或机器资源紧张时可能明显变慢，因此保留 **60 秒 inference read timeout**。

关键原则不是缩短 Ollama timeout，而是保证：

```text
inner timeout < outer timeout
```

### 14.1 Timeout Budget

| 环节 | Timeout | 说明 |
|------|---------|------|
| Ollama TCP connect | 3s | Ollama 未启动应快速失败 |
| Ollama write | 10s | 请求发送 |
| Ollama inference read | **60s** | 本地模型推理允许较慢 |
| Browser EXECUTE | 10s | 页面动作应较快完成 |
| Music Agent Task Budget | 75s | Ollama + Browser + 内部处理余量 |
| Main Agent → Music Agent A2A | 80s | 必须长于 Music Agent budget |
| `/chat` 整体预算 | 90s | 给路由、A2A 和 SSE 收尾留余量 |

### 14.2 httpx 示例

```python
OLLAMA_TIMEOUT = httpx.Timeout(
    connect=3.0,
    read=60.0,
    write=10.0,
    pool=5.0,
)
```

### 14.3 为什么 UI 仍然可接受

长 inference timeout 不代表 UI 静默等待。主 Agent 会通过 SSE 状态事件持续告诉用户任务处于：

```text
routing → thinking → executing → completed/failed
```

---

## 十五、异常流程

### 15.1 主 Agent 未启动

```text
Background POST /chat 失败
        ↓
Side Panel
“主 Agent 服务未响应，请确认 localhost:8001 已启动”
```

Background WebSocket 同时指数退避重连。

### 15.2 Music Agent 未启动

```text
Main Agent A2A 请求失败
        ↓
SSE error
“音乐控制服务未响应”
```

### 15.3 Ollama 未运行

connect timeout 3 秒快速失败：

```text
Music Agent
 ↓
Task.failed
 ↓
error.code = OLLAMA_UNAVAILABLE
```

### 15.4 Ollama 推理超过 60 秒

```text
Music Agent
 ↓
Task.failed
 ↓
error.code = OLLAMA_INFERENCE_TIMEOUT
```

### 15.5 Browser Gateway 未连接

```text
Browser Broker 查不到 browserSessionId
 ↓
Browser execute failed
 ↓
Music Agent Task.failed
 ↓
“浏览器控制通道未连接，请确认扩展已启用”
```

### 15.6 Content Script 未注入

```text
Background chrome.tabs.sendMessage
 ↓
Receiving end does not exist
 ↓
RESULT.success=false
error.code=CONTENT_SCRIPT_NOT_AVAILABLE
```

### 15.7 目标 Tab 已关闭

```text
executionContextId → tabId
 ↓
Chrome 查询 tab 失败
 ↓
TARGET_TAB_NOT_FOUND
```

### 15.8 页面不支持目标 capability

```text
music.set_volume
 ↓
Context capabilities 不包含 music.set_volume
 ↓
CAPABILITY_NOT_SUPPORTED
```

---

## 十六、安全设计

BrowserCompanion 的 localhost 服务实际上具有浏览器控制能力，因此必须把它当作本地控制 API，而不是普通 Demo HTTP Server。

### 16.1 网络绑定

默认只绑定：

```text
127.0.0.1
```

不默认监听：

```text
0.0.0.0
```

### 16.2 Extension ↔ Main Agent 鉴权

安装/首次启动时生成本地 session secret：

```text
Extension Storage
     ↕
Main Agent local config
```

HTTP 和 WebSocket 使用 token：

```text
Authorization: Bearer <local-session-token>
```

### 16.3 WebSocket Origin 校验

Browser `/browser/ws`：

- 校验 Extension origin
- 校验 token
- 校验 protocolVersion
- 一个 browserSessionId 只允许一个活跃连接

### 16.4 Internal Browser Execute API

`/internal/browser/execute` 不对任意网页开放。

至少校验：

- localhost only
- Agent credential / service token
- Agent namespace allowlist
- executionContextId TTL
- capability
- action schema

### 16.5 CORS

不使用：

```python
allow_origins=["*"]
```

只允许 Chrome Extension origin 和必要的 localhost 调试来源。

---

## 十七、目录结构

```text
browsercompanion/
│
├── extension/
│   ├── manifest.json
│   ├── background/
│   │   ├── index.js                     # Browser Gateway 入口
│   │   ├── agent-connection.js          # 主 Agent WebSocket + HTTP
│   │   ├── browser-session.js           # browserSessionId / heartbeat
│   │   ├── tab-router.js                 # tab/frame 路由
│   │   └── protocol.js                   # EXECUTE / RESULT 消息模型
│   ├── sidepanel/
│   │   ├── index.html
│   │   ├── style.css
│   │   └── app.js
│   ├── content/
│   │   ├── bridge.js
│   │   └── adapters/
│   │       └── netease-player.js
│   └── icons/
│
├── main_agent/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env
│   ├── chat.py
│   ├── config.py
│   ├── mimo_api.py
│   ├── intent/
│   │   ├── router.py
│   │   └── prompts.py
│   ├── agents/
│   │   ├── registry.py
│   │   └── a2a_client.py
│   ├── browser/
│   │   ├── models.py
│   │   ├── ws_router.py
│   │   ├── session_manager.py
│   │   ├── context_registry.py
│   │   └── execution_broker.py
│   └── reply/
│       ├── renderer.py
│       └── llm_reply.py
│
├── music_agent/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env
│   ├── a2a/
│   │   ├── models.py
│   │   ├── server.py
│   │   └── agent_card.py
│   ├── actions/
│   │   ├── models.py                    # Pydantic Action Schema
│   │   ├── confidence.py                # confidence policy
│   │   └── parser.py                    # Ollama → Action
│   ├── browser/
│   │   └── execution_client.py          # 调主 Agent Browser Broker
│   └── ollama_client.py
│
└── docs/
    └── architecture.md
```

---

## 十八、Chrome Extension 配置

### 18.1 manifest.json

```json
{
  "manifest_version": 3,
  "name": "BrowserCompanion",
  "version": "1.1.0",
  "description": "AI 伴随式浏览器控制助手",
  "permissions": [
    "sidePanel",
    "activeTab",
    "tabs",
    "storage"
  ],
  "host_permissions": [
    "https://music.163.com/*",
    "http://127.0.0.1:8001/*",
    "http://localhost:8001/*"
  ],
  "side_panel": {
    "default_path": "sidepanel/index.html"
  },
  "background": {
    "service_worker": "background/index.js"
  },
  "content_scripts": [{
    "matches": ["https://music.163.com/*"],
    "js": ["content/bridge.js", "content/adapters/netease-player.js"],
    "run_at": "document_idle",
    "all_frames": true
  }],
  "action": {
    "default_title": "打开 BrowserCompanion"
  }
}
```

> WebSocket 连接由 Background 发起到主 Agent；Content Script 不再连接 localhost WebSocket。

---

## 十九、协议模型

### 19.1 Browser Gateway WebSocket

REGISTER：

```json
{
  "type": "REGISTER",
  "browserSessionId": "browser-001",
  "protocolVersion": "1.0"
}
```

PING / PONG：

```json
{"type":"PING","ts":1730000000}
{"type":"PONG","ts":1730000000}
```

EXECUTE：

```json
{
  "type": "EXECUTE",
  "requestId": "req-001",
  "target": {
    "tabId": 123,
    "frameId": 0
  },
  "action": {
    "namespace": "music",
    "name": "pause",
    "params": {}
  }
}
```

RESULT：

```json
{
  "type": "RESULT",
  "requestId": "req-001",
  "success": true,
  "data": {
    "paused": true
  }
}
```

### 19.2 Error 模型

统一错误：

```json
{
  "code": "AUDIO_NOT_FOUND",
  "message": "未找到可控制的播放器",
  "retryable": false,
  "details": {}
}
```

建议错误码：

```text
MAIN_AGENT_UNAVAILABLE
DOMAIN_AGENT_UNAVAILABLE
OLLAMA_UNAVAILABLE
OLLAMA_INFERENCE_TIMEOUT
ACTION_PARSE_FAILED
ACTION_SCHEMA_INVALID
LOW_CONFIDENCE
EXECUTION_CONTEXT_EXPIRED
BROWSER_GATEWAY_OFFLINE
TARGET_TAB_NOT_FOUND
CONTENT_SCRIPT_NOT_AVAILABLE
CAPABILITY_NOT_SUPPORTED
ACTION_EXECUTION_TIMEOUT
AUDIO_NOT_FOUND
DOM_TARGET_NOT_FOUND
```

---

## 二十、运行时依赖与启动

### 20.1 运行时依赖

| 组件 | 依赖 | 配置 / 启动方式 |
|------|------|----------------|
| **Chrome Extension** | Chrome MV3 | 开发者模式加载 `extension/` |
| **主 Agent** | Python 3.11+、FastAPI、httpx、websockets / FastAPI WebSocket | `uvicorn main:app --host 127.0.0.1 --port 8001` |
| **Music Agent** | Python 3.11+、FastAPI、httpx、pydantic | `uvicorn main:app --host 127.0.0.1 --port 8000` |
| **MiMo API** | 网络 + API Key | 主 Agent 通用对话 / 复杂路由 |
| **Ollama** | Ollama + `qwen2.5:7b-instruct` | 默认 `127.0.0.1:11434` |

### 20.2 主 Agent 环境变量

```text
MIMO_ENDPOINT=https://api.xiaomimimo.com/v1/chat/completions
MIMO_API_KEY=your_api_key_here
MUSIC_AGENT_URL=http://127.0.0.1:8000

# Extension ↔ Main Agent
EXTENSION_SESSION_TOKEN=<local-random-token>

# Domain Agent → Browser Execution Broker
BROWSER_EXECUTION_SERVICE_TOKEN=<local-service-token>

# Timeout budget
A2A_TIMEOUT_SECONDS=80
CHAT_TASK_BUDGET_SECONDS=90
BROWSER_EXECUTION_TIMEOUT_SECONDS=10
```

### 20.3 Music Agent 环境变量

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b-instruct

BROWSER_EXECUTION_URL=http://127.0.0.1:8001/internal/browser/execute
BROWSER_EXECUTION_SERVICE_TOKEN=<same-local-service-token>

OLLAMA_CONNECT_TIMEOUT_SECONDS=3
OLLAMA_READ_TIMEOUT_SECONDS=60
MUSIC_TASK_BUDGET_SECONDS=75
```

### 20.4 完整启动顺序

```text
1. ollama serve
2. ollama pull qwen2.5:7b-instruct        # 首次运行
3. 启动 Music Agent :8000
4. 启动 Main Agent  :8001
5. Chrome 加载 extension/
6. Background Browser Gateway 连接 /browser/ws 并 REGISTER
7. 打开 https://music.163.com/...
8. Content Script 上报页面 capabilities
9. 打开 Side Panel 开始对话
```

启动顺序中 Music Agent 可以先于或晚于 Main Agent 启动；Agent Registry 应允许健康状态动态变化。但真正执行音乐任务前，主 Agent 必须确认 Music Agent 可用，Browser Gateway 也必须已经注册。

---

## 二十一、端点汇总

### 21.1 主 Agent（127.0.0.1:8001）

| 端点 | 协议 / 方法 | 调用方 | 说明 |
|------|-------------|--------|------|
| `/chat` | HTTP POST + SSE | Extension Background | 用户对话入口 |
| `/browser/ws` | WebSocket | Extension Background | Browser Gateway 持久执行通道 |
| `/internal/browser/execute` | HTTP POST | Domain Agents | 浏览器执行基础设施 RPC |
| `/health` | HTTP GET | 本地诊断 / Agent | 主 Agent 健康检查 |

### 21.2 Music Agent（127.0.0.1:8000）

| 端点 | 协议 / 方法 | 调用方 | 说明 |
|------|-------------|--------|------|
| `/.well-known/agent.json` | HTTP GET | Main Agent | Agent Card / capability discovery |
| `/a2a` | JSON-RPC over HTTP POST | Main Agent | A2A Task 入口 |
| `/health` | HTTP GET | Main Agent | Music Agent / Ollama 状态摘要 |

### 21.3 端点边界约束

`/internal/browser/execute` 是内部基础设施接口，不作为公网 API，不由 Side Panel 或普通网页直接调用。Domain Agent 只能通过 service token 调用，并且必须携带有效 `executionContextId`。

`/browser/ws` 只接受 Extension Browser Gateway 注册，不接受 Content Script 直接连接。

---

## 二十二、实现顺序

| 阶段 | 内容 | 验证方式 |
|------|------|---------|
| **Phase 1** | Extension 骨架 + Side Panel + Background Browser Gateway | UI 可打开；Background 可获取 active tab |
| **Phase 2** | Background ↔ Main Agent WebSocket + browser session | REGISTER / PING / reconnect 正常 |
| **Phase 3** | Content Script + NeteasePlayerAdapter + tab 精确路由 | 指定 tabId 的 pause 只影响目标 Tab |
| **Phase 4** | Main Agent Browser Execution Broker | HTTP execute → WS → Content Script → RESULT 闭环 |
| **Phase 5** | Music Agent A2A + Ollama + Action Schema | 自然语言稳定生成合法 music.* Action |
| **Phase 6** | confidence policy + A2A state lifecycle | 低 confidence 不执行；页面失败时 Task.failed |
| **Phase 7** | `/chat` Orchestrator + SSE 状态事件 | routing/thinking/executing/result 全链路可见 |
| **Phase 8** | 多标签页 + 错误处理 + 安全鉴权 | 两个网易云 Tab 不发生广播误控制 |
| **Phase 9** | Agent Registry + 第二个垂域 Agent | 验证 A2A 多 Agent 架构可扩展 |

---

## 二十三、技术风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|---------|
| Ollama 本地推理较慢 | 用户等待时间长 | inference read timeout=60s；SSE 状态持续反馈；后续增加 fast path |
| Ollama 输出非法 JSON | 错误动作 | 严格 JSON + Pydantic Schema；解析失败禁止默认执行 |
| Ollama 语义不确定 | 误操作 | confidence policy；低于 0.60 请求澄清 |
| 多个网易云标签页 | 动作执行到错误页面 | executionContextId + browserSessionId + tabId + frameId 精确路由 |
| Background Service Worker 被 Chrome suspend | WS 中断 | reconnect + session re-register + pending request timeout |
| 网易云 `<audio>` / DOM 结构变化 | 执行动作失败 | Site Adapter + capability probe + 多策略 fallback |
| iframe / Shadow DOM | 无法直接操作 | all_frames；同源 frame；Site Adapter；不把 `<audio>` 当唯一 backend |
| Browser Gateway 断连 | Domain Agent 无法执行 | Broker session 状态 + 快速失败 + UI 明确提示 |
| Main Agent Browser Broker 被恶意网页调用 | 浏览器被远程控制 | localhost bind、token、Origin、context TTL、namespace allowlist |
| 父 timeout 小于子 timeout | 主 Agent提前失败 | 固定 Timeout Budget：60 < 75 < 80 < 90 |
| Browser RESULT 丢失 | Task 悬挂 | requestId Future + 10s execution timeout + finally 清理 |
| Agent 扩展后 Action 名冲突 | 路由错误 | namespace.action 统一命名 |

---

## 二十四、后续优化方向

### 24.1 Fast Path

对于高度确定的简单指令：

```text
暂停
继续播放
下一首
音量50%
```

未来可以在 Music Agent 内增加 deterministic parser：

```text
Rule / Parser 命中
    ↓
直接生成 Action

未命中
    ↓
Ollama
```

这样既保留本地 LLM 的自然语言理解能力，又减少简单命令的推理延迟。

### 24.2 Agent Registry

主 Agent 后续根据 Agent Card 自动维护：

```text
agent id
endpoint
skills
tags
health
supported namespaces
```

路由不再硬编码 `if music_control`。

### 24.3 Browser Capability Registry

Browser Gateway 定期上报页面能力：

```text
browserSession
 └── tab 123
      ├── music.play
      ├── music.pause
      └── music.set_volume
```

主 Agent 可以在调用垂域 Agent 之前先判断目标页面是否具备必要能力。

---

## 二十五、最终架构原则

本方案最终遵循以下边界：

```text
Main Agent
负责“交给谁做”

Domain Agent
负责“应该做什么”

Browser Execution Broker / Gateway
负责“把动作送到哪个浏览器页面”

Content Script / Site Adapter
负责“具体怎么操作页面”
```

即：

```text
Natural Language
      ↓
Main Agent Orchestration
      ↓ A2A
Domain Agent Reasoning
      ↓
Validated Structured Action
      ↓
Browser Execution Broker
      ↓ WebSocket
Background Browser Gateway
      ↓ chrome.tabs.sendMessage
Content Script
      ↓
Site Adapter
      ↓
DOM / HTMLMediaElement
```

这套结构能够在保留 A2A 多垂域 Agent 扩展能力的同时，将浏览器连接、标签页路由、动作安全和页面适配收敛到清晰的基础设施边界中。
