# NagaAgent Game 模块化重构说明

本文档包含当前 `game` 目录树、各文件功能清单、已发现的冗余/风险点，以及遵循“动态生成、无枚举、职责清晰”原则的模块化优化方案与任务清单。  #

## 目录树

```text
game/
  __init__.py
  ARCHITECTURE_UPDATE.md
  ARCHITECTURE_REFACTOR.md  ← 本文件
  README.md
  REQUIREMENTS.md
  config.json.example
  core/
    __init__.py
    interaction_graph/
      __init__.py
      distributor.py
      dynamic_dispatcher.py
      prompt_generator.py
      role_generator.py
      signal_router.py
      user_interaction_handler.py
    self_game/
      __init__.py
      actor.py
      criticizer.py
      game_engine.py
      checker/
        __init__.py
        philoss_checker.py
  examples/
    basic_usage.py
    components_test.py
    self_game_demo.py
    user_question_demo.py
  full_flow_test.py
  naga_game_system.py
  
```

## 各文件功能清单

### 顶层
- `README.md`：模块使用与概述  #
- `REQUIREMENTS.md`：依赖说明  #
- `config.json.example`：示例配置（含 system/self_game/interaction_graph/domain_configs 等）  #
- `config_test.py`：`GameConfig` 适配/验证/序列化测试  #
- `core_validation.py`：验证核心数据模型/无枚举原则/需求方节点  #
- `full_flow_test.py`：使用 `MockNagaConversation` 的端到端流程测试（角色→权限→Prompt→Actor/Critic/Checker）  #
- `integration_test.py`：配置与数据模型集成验证、枚举原则等  #
- `minimal_test.py`：最小化数据模型/配置测试  #
- `naga_game_system.py`：高层系统封装，提供从问题到博弈的流程接口  #
- `simple_test.py`：简化异步测试集合  #

### core/
- `core/__init__.py`：聚合导出  #

#### core/interaction_graph/
- `distributor.py`：角色分配器  #
  - LLM 生成角色（JSON：name/role_type/responsibilities/skills/output_requirements/priority_level）  #
  - LLM 生成协作权限（JSON：permissions 映射）  #
  - 回退：严格JSON重试→无API占位角色  #
- `prompt_generator.py`：提示词生成器  #
  - 为每个角色生成 system prompt（正文，不是JSON），包含：身份定位/职责/协作方式/输出要求/边界  #
  - 无API回退：结构化占位 prompt  #
- `role_generator.py`：整合生成流程  #
  - 生成角色 → 分配权限 → 为每个角色生成 system prompt → 创建 `Agent`  #
  - 程序端创建“需求方”节点，并连接至最高优先级执行者  #
  - 验证智能体数量/唯一性/字段完整性  #
  - 优先级估算：若无 `priority_level`，尝试LLM给出1..10，否则默认5  #
- `signal_router.py`：信号路由器  #
  - 基于各 `Agent.connection_permissions` 构建允许路径  #
  - 默认允许执行者自环，`forbidden_paths` 目前留空  #
  - 校验路径有效/冲突，提供通信矩阵与可视化  #
- `dynamic_dispatcher.py`：动态分发器  #
  - 根据任务输出与需求，动态选择目标智能体  #
  - 近日已移除固定角色映射，改为职责/技能启发式匹配与通用“协调者”启发式  #
  - 维护分发历史与迭代计数，限制过度迭代并可抛出超限异常  #
- `user_interaction_handler.py`：用户交互处理  #
  - 校验交互图结构，识别需求方与首个执行者  #
  - 构建面向执行者的强约束答复提示，优先LLM生成，否则回退  #
  - 统一封装 `SystemResponse` 并记录会话  #

#### core/self_game/
- `actor.py`：Actor 组件  #
  - 为执行者生成本轮内容（带历史摘要/上下文），LLM优先，降级回退  #
  - 记录生成时长/迭代次序/元数据  #
- `criticizer.py`：Criticizer 组件  #
  - 对 Actor 输出进行多维度批判（创新/逻辑/完整/可行/质量/相关），给出总体分、满意度与建议  #
  - LLM优先，失败使用模拟JSON  #
- `checker/philoss_checker.py`：创新性评估  #
  - 100-token 切块，抽取隐藏状态，计算状态预测误差→Novel score  #
  - 无模型时走“模拟分数”，并保留统计  #
- `game_engine.py`：自博弈引擎  #
  - 组织 Actor→Criticizer→Checker 的 1:n:1 闭环多轮迭代  #
  - 终止条件：迭代上限/质量阈值/收敛阈值/新颖度阈值/缺失阶段  #
  - 计算质量指标并输出 `GameResult`  #

### examples/
- `basic_usage.py`：基础演示：角色生成→构图→可视化/统计  #
- `components_test.py`：独立测试 Distributor/PromptGenerator 与数据模型  #
- `self_game_demo.py`：Actor/Criticizer/Checker 组件演示（包含重复片段，建议精简）  #
- `user_question_demo.py`：用户问题到角色与处理示例  #

## 已发现的冗余/风险点
- 配置文件 `config.json.example` 存在重复块（文件尾部出现重复 system/self_game/interaction_graph/domain_configs 片段），建议去重校正  #
- `examples/self_game_demo.py` 有较多重复定义与内容拷贝，建议整合为一次性清晰示例  #
- `dynamic_dispatcher.py` 原有固定角色兼容度表与固定阶段分支已移除，统一改为动态启发式；如需LLM化评分，建议新增接口  #
- `signal_router.py` 的 `forbidden_paths` 目前始终为空，尚未体现“禁止直连”策略（如需可通过策略或LLM生成再校验）  #

## 模块化优化方案

围绕“交互图生成器 / 自博弈模块 / 共识记忆（预留）”三大核心进行分层与解耦，最小化修改现有稳定可跑路径。  #

### A. 交互图生成器（初始化驱动）
目标：统一入口、严格无枚举、接口收敛。  #

- A1 统一入口
  - 保持 `RoleGenerator` 为唯一入口：内部编排 Distributor→权限→Prompt→Agent→Requester→权限回写  #
  - 输出：`List[Agent]`（含需求方），供路由与博弈模块复用  #

- A2 角色/权限/Prompt 动态化约束
  - Distributor 提示词已禁止“需求方/用户/客户”，保留  #
  - 权限分配 LLM 输出 JSON；失败回退默认规则（现已实现）  #
  - PromptGenerator 仅输出 system prompt 正文；失败回退结构化模板（现已实现）  #

- A3 信号路由
  - `SignalRouter` 继续以 `connection_permissions` 为主构图  #
  - 新增“禁止直连策略”可选层：
    - 策略版：基于职责相似度/阶段跨越进行禁止边生成  #
    - LLM版：输入角色清单/职责/权限草案，请LLM输出禁止边，然后校验并去冲突  #

### B. 动态传输（执行期调度）
目标：去除硬编码、支持 LLM 评分可插拔、保持可跑的降级路径。  #

- B1 下一阶段需求分析
  - 现为启发式：从 `task_output/responsibilities/skills` 提取关键词→`required_skills/output_type/collaboration_type`  #
  - 可选：提供 LLM 判定接口（失败回退启发式）  #

- B2 角色兼容性分数
  - 已移除固定角色表；现为职责/技能匹配启发式  #
  - 可选：新增 LLM 打分接口（输入 required_skills + agent 描述/system prompt，输出 0..1），失败回退启发式  #

- B3 协调者检测
  - 已由固定名单→关键词启发式（manager/lead/负责人/coordinator/architect/owner）  #

### C. 自博弈模块（质量与创新性）
目标：保持 1:n:1 结构清晰，参数化收敛与阈值，兼容无模型模式。  #

- C1 Actor/Criticizer/Checker：保持当前结构与阈值机制，作为稳定基线  #
- C2 Philoss：继续支持无模型“模拟模式”；若环境可用则加载小模型+MLP  #
- C3 思维向量/思维栈：后续将“function-call 更新思维向量”纳入统一提示策略，由 Prompt 层和 GameEngine 注入  #

### D. 文档与示例
目标：精简重复、统一入口示例、保证中文友好。  #

- D1 文档
  - 本文件与 `ARCHITECTURE_UPDATE.md` 分工：前者“现状+优化方案”，后者“版本变更/演进说明”  #
- D2 示例
  - 合并 `self_game_demo.py` 重复段，保留一份“端到端最小示例”和“组件级示例”  #
- D3 配置
  - 修复 `config.json.example` 重复片段，保留单份规范结构  #

## 建议落地任务清单

短期（不破坏可跑路径）：  #
- [ ] 修复 `config.json.example` 重复字段块  #
- [ ] 在 `SignalRouter` 增加可选“禁止直连策略”钩子（默认不开启）  #
- [ ] `DynamicDispatcher` 增加 LLM 评分可插拔接口（默认走启发式，失败回退不影响运行）  #
- [ ] 精简 `examples/self_game_demo.py` 重复代码，统一示例入口  #

中期（功能增强）：  #
- [ ] 将“下一阶段需求分析”支持 LLM 判定（失败回退启发式）  #
- [ ] 在 Prompt 体系注入“思维向量/思维栈”统一段落与 function-call 更新占位  #
- [ ] 可选接入“共识记忆/Graph RAG”模块，并与博弈输出/批判建议建立图谱关联  #

长期（体系化）：  #
- [ ] 会话/状态统一管理（SessionManager）  #
- [ ] 统一日志/埋点/指标导出，分组件统计聚合  #
- [ ] 统一错误降级策略文档化与可配置化  #

---

如需我按照该方案逐步提交最小粒度的安全编辑，请点名优先级（例如：先修复配置文件重复与示例精简，再加分发器LLM评分接口）。  #


