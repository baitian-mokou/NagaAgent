"""
GameCriticizer - 批判优化组件

负责对Actor输出的初始成果进行多维度批判,精准识别逻辑漏洞、创新性不足、
细节缺失等问题,并针对性地提出优化建议,同时为成果表现和建议满意度进行打分.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..models.data_models import Agent, Task
from ..models.config import GameConfig
from .actor import ActorOutput

logger = logging.getLogger(__name__)


class CriticDimension(Enum):
    """批判维度枚举"""
    INNOVATION = "创新性"
    LOGIC = "逻辑性" 
    COMPLETENESS = "完整性"
    FEASIBILITY = "可行性"
    QUALITY = "质量"
    RELEVANCE = "相关性"


@dataclass
class CriticScore:
    """批判评分"""
    dimension: CriticDimension
    score: float  # 0-10分
    reasoning: str  # 评分理由
    suggestions: List[str]  # 改进建议


@dataclass
class CriticOutput:
    """Criticizer组件的输出结果"""
    target_output_id: str  # 目标ActorOutput的ID
    critic_agent_id: str  # 批判者的智能体ID
    overall_score: float  # 总体评分 (Critical score)
    satisfaction_score: float  # 满意度评分 (Satisfaction score)
    dimension_scores: List[CriticScore]  # 各维度详细评分
    summary_critique: str  # 总体批判意见
    improvement_suggestions: List[str]  # 优化建议列表
    critique_time: float  # 批判耗时
    iteration: int  # 批判轮次
    metadata: Dict[str, Any]  # 额外元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'target_output_id': self.target_output_id,
            'critic_agent_id': self.critic_agent_id,
            'overall_score': self.overall_score,
            'satisfaction_score': self.satisfaction_score,
            'dimension_scores': [
                {
                    'dimension': score.dimension.value,
                    'score': score.score,
                    'reasoning': score.reasoning,
                    'suggestions': score.suggestions
                } for score in self.dimension_scores
            ],
            'summary_critique': self.summary_critique,
            'improvement_suggestions': self.improvement_suggestions,
            'critique_time': self.critique_time,
            'iteration': self.iteration,
            'metadata': self.metadata
        }


class GameCriticizer:
    """游戏Criticizer组件 - 批判优化器"""
    
    def __init__(self, config: GameConfig, naga_conversation=None):
        """
        初始化GameCriticizer
        
        Args:
            config: 游戏配置
            naga_conversation: NagaAgent的会话实例
        """
        self.config = config
        self.naga_conversation = naga_conversation
        self.critique_history: List[CriticOutput] = []
        self.current_iteration = 0
        self._init_naga_api()
    
    def _init_naga_api(self):
        """初始化NagaAgent API连接"""
        if self.naga_conversation is None:
            try:
                from system.conversation_core import NagaConversation
                self.naga_conversation = NagaConversation()
                logger.info("GameCriticizer成功初始化NagaAgent API连接")
            except ImportError as e:
                logger.error(f"GameCriticizer无法导入NagaAgent API: {e}")
                # 不抛出异常,允许模拟模式运行
    
    async def critique_output(self, 
                             actor_output: ActorOutput, 
                             critic_agent: Agent,
                             task: Task,
                             previous_critiques: Optional[List[CriticOutput]] = None) -> CriticOutput:
        """
        批判Actor输出的内容
        
        Args:
            actor_output: 需要批判的Actor输出
            critic_agent: 执行批判的智能体
            task: 任务描述
            previous_critiques: 之前的批判结果（用于评估满意度）
            
        Returns:
            批判输出结果
        """
        start_time = time.time()
        self.current_iteration += 1
        
        try:
            logger.info(f"Criticizer开始批判:{critic_agent.name} 批判 {actor_output.agent_id}")
            
            # 构建批判提示词
            critique_prompt = self._build_critique_prompt(
                actor_output, critic_agent, task, previous_critiques
            )
            
            # 调用大模型进行批判分析
            critique_result = await self._call_llm_for_critique(critique_prompt, critic_agent)
            
            # 解析批判结果
            dimension_scores, overall_score, summary_critique, suggestions = self._parse_critique_result(
                critique_result, actor_output, task
            )
            
            # 计算满意度评分
            satisfaction_score = self._calculate_satisfaction_score(
                previous_critiques, dimension_scores
            )
            
            # 创建批判输出
            critique_output = CriticOutput(
                target_output_id=f"{actor_output.agent_id}_{actor_output.iteration}",
                critic_agent_id=critic_agent.agent_id,
                overall_score=overall_score,
                satisfaction_score=satisfaction_score,
                dimension_scores=dimension_scores,
                summary_critique=summary_critique,
                improvement_suggestions=suggestions,
                critique_time=time.time() - start_time,
                iteration=self.current_iteration,
                metadata={
                    'target_agent_name': actor_output.metadata.get('agent_name', 'unknown'),
                    'critic_agent_name': critic_agent.name,
                    'task_domain': task.domain,
                    'has_previous_critiques': previous_critiques is not None and len(previous_critiques) > 0,
                    'content_length': len(actor_output.content)
                }
            )
            
            # 记录到历史
            self.critique_history.append(critique_output)
            
            logger.info(f"Criticizer完成批判,总分{overall_score:.1f},满意度{satisfaction_score:.1f}")
            return critique_output
            
        except Exception as e:
            logger.error(f"Criticizer批判失败:{e}")
            # 返回错误批判
            return CriticOutput(
                target_output_id=f"{actor_output.agent_id}_{actor_output.iteration}",
                critic_agent_id=critic_agent.agent_id,
                overall_score=5.0,  # 中等评分
                satisfaction_score=5.0,
                dimension_scores=[],
                summary_critique=f"批判过程出错:{str(e)}",
                improvement_suggestions=["建议重新进行批判分析"],
                critique_time=time.time() - start_time,
                iteration=self.current_iteration,
                metadata={'error': True, 'error_message': str(e)}
            )
    
    def _build_critique_prompt(self, 
                              actor_output: ActorOutput, 
                              critic_agent: Agent, 
                              task: Task,
                              previous_critiques: Optional[List[CriticOutput]] = None) -> str:
        """构建批判分析的提示词"""
        
        prompt_sections = [
            f"# 批判专家身份\n{critic_agent.system_prompt}\n",
            
            f"# 批判任务\n你需要对以下内容进行专业的多维度批判分析:\n",
            
            f"## 原始任务背景\n",
            f"- 任务ID:{task.task_id}\n",
            f"- 任务描述:{task.description}\n", 
            f"- 任务领域:{task.domain}\n"
        ]
        
        # 添加任务需求和约束
        if task.requirements:
            prompt_sections.append("- 任务需求:" + "、".join(task.requirements) + "\n")
        if task.constraints:
            prompt_sections.append("- 约束条件:" + "、".join(task.constraints) + "\n")
        
        # 添加待批判的内容
        prompt_sections.extend([
            f"\n## 待批判内容\n",
            f"**作者**:{actor_output.metadata.get('agent_name', '未知')}\n",
            f"**迭代轮次**:第{actor_output.iteration}轮\n",
            f"**生成时间**:{actor_output.generation_time:.2f}秒\n",
            f"**内容**:\n```\n{actor_output.content}\n```\n"
        ])
        
        # 添加历史批判参考
        if previous_critiques:
            prompt_sections.append("\n## 历史批判参考\n")
            for i, prev_critique in enumerate(previous_critiques[-2:], 1):  # 只显示最近2次
                prompt_sections.append(f"### 第{prev_critique.iteration}轮批判:\n")
                prompt_sections.append(f"- 总体评分:{prev_critique.overall_score:.1f}/10\n")
                prompt_sections.append(f"- 主要意见:{prev_critique.summary_critique[:100]}...\n")
        
        # 添加批判维度说明
        prompt_sections.extend([
            f"\n# 批判维度要求\n",
            f"请从以下6个维度对内容进行评分（0-10分）和分析:\n",
            f"1. **创新性**:内容是否具有新颖的思路和独特的见解\n",
            f"2. **逻辑性**:论证是否严密,结构是否合理\n", 
            f"3. **完整性**:内容是否全面,是否遗漏重要方面\n",
            f"4. **可行性**:方案是否具有实际操作性和可执行性\n",
            f"5. **质量**:内容的专业水准和表达质量\n",
            f"6. **相关性**:内容与任务需求的匹配程度\n"
        ])
        
        # 添加输出格式要求
        prompt_sections.extend([
            f"\n# 输出格式要求\n",
            f"请严格按照以下JSON格式输出批判结果:\n",
            f"```json\n",
            f"{{\n",
            f'  "dimension_scores": [\n',
            f'    {{"dimension": "创新性", "score": 7.5, "reasoning": "评分理由", "suggestions": ["建议1", "建议2"]}},\n',
            f'    {{"dimension": "逻辑性", "score": 8.0, "reasoning": "评分理由", "suggestions": ["建议1"]}},\n',
            f'    ...\n',
            f'  ],\n',
            f'  "overall_score": 7.8,\n',
            f'  "summary_critique": "总体批判意见,包含主要优点和不足",\n',
            f'  "improvement_suggestions": ["具体改进建议1", "具体改进建议2", "具体改进建议3"]\n',
            f"}}\n```\n"
        ])
        
        # 添加批判原则
        prompt_sections.extend([
            f"\n# 批判原则\n",
            f"1. **客观公正**:基于内容质量进行评价,避免主观偏见\n",
            f"2. **建设性**:不仅指出问题,更要提供改进方向\n",
            f"3. **专业性**:运用{critic_agent.role}的专业知识进行分析\n",
            f"4. **针对性**:针对{task.domain}领域的特点进行评价\n",
            f"5. **发展性**:考虑内容的发展潜力和优化空间\n"
        ])
        
        prompt_sections.append("\n请开始进行专业的批判分析:")
        
        return "\n".join(prompt_sections)
    
    async def _call_llm_for_critique(self, prompt: str, critic_agent: Agent) -> str:
        """调用大模型进行批判分析"""
        try:
            if self.naga_conversation is None:
                # 模拟模式
                return self._generate_mock_critique(critic_agent)
            
            # 实际API调用
            response = await self.naga_conversation.get_response(
                prompt,
                temperature=0.6  # 适中的温度,保证客观性
            )
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"批判LLM调用失败:{e}")
            return self._generate_mock_critique(critic_agent)
    
    def _generate_mock_critique(self, critic_agent: Agent) -> str:
        """生成模拟批判内容（用于测试和演示）"""
        mock_critiques = {
            "质量分析师": f"""{{
  "dimension_scores": [
    {{"dimension": "创新性", "score": 7.5, "reasoning": "提出了一些新颖的想法,但缺乏突破性创新", "suggestions": ["探索更前沿的技术方案", "结合最新行业趋势"]}},
    {{"dimension": "逻辑性", "score": 8.2, "reasoning": "整体逻辑清晰,论证较为严密", "suggestions": ["加强因果关系论证"]}},
    {{"dimension": "完整性", "score": 6.8, "reasoning": "主要内容齐全,但部分细节有待补充", "suggestions": ["补充实施细节", "增加风险评估"]}},
    {{"dimension": "可行性", "score": 7.0, "reasoning": "方案基本可行,但需要考虑实际约束", "suggestions": ["评估资源需求", "制定分阶段实施计划"]}},
    {{"dimension": "质量", "score": 7.8, "reasoning": "专业水准良好,表达清晰", "suggestions": ["优化文档结构", "增加可视化元素"]}},
    {{"dimension": "相关性", "score": 8.5, "reasoning": "与任务需求高度匹配", "suggestions": ["进一步细化需求对应关系"]}}
  ],
  "overall_score": 7.6,
  "summary_critique": "整体方案具有良好的专业基础和可行性,逻辑结构清晰,与任务需求匹配度高.主要优势在于专业性和相关性,但在创新性和完整性方面还有提升空间.建议加强前沿技术的探索,补充实施细节和风险评估.",
  "improvement_suggestions": ["增加创新技术方案的探索", "补充详细的实施计划和时间线", "加入风险评估和应对策略", "优化文档结构和可读性"]
}}""",

            "技术评审": f"""{{
  "dimension_scores": [
    {{"dimension": "创新性", "score": 6.5, "reasoning": "技术方案相对保守,创新点不够突出", "suggestions": ["引入新兴技术栈", "探索创新架构模式"]}},
    {{"dimension": "逻辑性", "score": 8.8, "reasoning": "技术逻辑严密,架构设计合理", "suggestions": ["完善异常处理逻辑"]}},
    {{"dimension": "完整性", "score": 7.2, "reasoning": "核心技术要素完备,但缺少部署和运维考虑", "suggestions": ["补充部署方案", "增加监控体系"]}},
    {{"dimension": "可行性", "score": 8.0, "reasoning": "技术方案成熟可靠,实施风险较低", "suggestions": ["评估性能瓶颈", "制定扩容策略"]}},
    {{"dimension": "质量", "score": 7.5, "reasoning": "技术文档规范,但可视化不足", "suggestions": ["增加架构图", "完善API文档"]}},
    {{"dimension": "相关性", "score": 8.3, "reasoning": "技术选型符合项目需求", "suggestions": ["优化技术栈匹配度"]}}
  ],
  "overall_score": 7.7,
  "summary_critique": "技术方案整体稳健可靠,架构设计合理,逻辑严密.在可行性和相关性方面表现优秀,但创新性有待提升.建议引入更多前沿技术,完善部署运维方案,增强文档的可视化表达.",
  "improvement_suggestions": ["探索微服务架构的创新实践", "补充完整的部署和运维方案", "增加系统架构图和流程图", "建立性能监控和告警体系"]
}}""",

            "产品评估": f"""{{
  "dimension_scores": [
    {{"dimension": "创新性", "score": 8.0, "reasoning": "产品理念新颖,用户体验有创新点", "suggestions": ["深化差异化特性", "探索新交互模式"]}},
    {{"dimension": "逻辑性", "score": 7.5, "reasoning": "产品逻辑基本清晰,但部分流程需优化", "suggestions": ["简化用户操作流程", "优化信息架构"]}},
    {{"dimension": "完整性", "score": 6.9, "reasoning": "核心功能完备,但缺少边界场景考虑", "suggestions": ["补充异常场景处理", "完善用户反馈机制"]}},
    {{"dimension": "可行性", "score": 7.8, "reasoning": "产品方案可行,符合市场需求", "suggestions": ["评估开发成本", "制定MVP方案"]}},
    {{"dimension": "质量", "score": 7.3, "reasoning": "产品设计专业,但细节需打磨", "suggestions": ["优化界面设计", "完善交互细节"]}},
    {{"dimension": "相关性", "score": 8.7, "reasoning": "高度符合用户需求和市场定位", "suggestions": ["加强用户画像分析"]}}
  ],
  "overall_score": 7.7,
  "summary_critique": "产品方案创新性较强,市场定位准确,用户需求匹配度高.在创新性和相关性方面表现突出,但在完整性和细节打磨方面需要加强.建议深化产品差异化特性,完善边界场景处理,优化用户体验细节.",
  "improvement_suggestions": ["深化产品差异化竞争优势", "完善用户场景和边界情况处理", "优化产品原型和交互设计", "建立用户反馈和迭代机制"]
}}"""
        }
        
        # 根据批判者角色选择模拟内容
        for role_key, critique in mock_critiques.items():
            if role_key in critic_agent.name or role_key in critic_agent.role:
                return critique
        
        # 默认模拟批判
        return f"""{{
  "dimension_scores": [
    {{"dimension": "创新性", "score": 7.0, "reasoning": "具有一定创新性,但突破性不够", "suggestions": ["探索更具突破性的方案"]}},
    {{"dimension": "逻辑性", "score": 7.5, "reasoning": "逻辑基本清晰,论证较为合理", "suggestions": ["加强逻辑链条的完整性"]}},
    {{"dimension": "完整性", "score": 6.8, "reasoning": "主要内容完备,细节有待补充", "suggestions": ["补充实施细节和边界情况"]}},
    {{"dimension": "可行性", "score": 7.2, "reasoning": "方案基本可行,需考虑实际约束", "suggestions": ["评估实施难度和资源需求"]}},
    {{"dimension": "质量", "score": 7.3, "reasoning": "专业水准良好,表达清晰", "suggestions": ["优化内容结构和表达方式"]}},
    {{"dimension": "相关性", "score": 8.0, "reasoning": "与任务需求匹配度较高", "suggestions": ["进一步对齐具体需求"]}}
  ],
  "overall_score": 7.3,
  "summary_critique": "作为{critic_agent.role},我认为这个方案整体质量良好,与任务需求匹配度高,逻辑结构基本清晰.主要优势在于相关性和专业性,但在创新性和完整性方面还有改进空间.建议加强突破性思维,完善实施细节.",
  "improvement_suggestions": ["增强方案的创新性和前瞻性", "补充详细的实施计划和风险评估", "优化内容结构和表达质量", "加强与任务需求的精确对应"]
}}"""
    
    def _parse_critique_result(self, 
                              critique_result: str, 
                              actor_output: ActorOutput, 
                              task: Task) -> Tuple[List[CriticScore], float, str, List[str]]:
        """解析批判结果"""
        try:
            import json
            import re
            
            # 提取JSON部分
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', critique_result, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = critique_result.strip()
                if not json_str.startswith('{'):
                    # 查找第一个{到最后一个}
                    start = json_str.find('{')
                    end = json_str.rfind('}') + 1
                    if start != -1 and end > start:
                        json_str = json_str[start:end]
            
            data = json.loads(json_str)
            
            # 解析维度评分
            dimension_scores = []
            if 'dimension_scores' in data:
                for score_data in data['dimension_scores']:
                    try:
                        dimension = CriticDimension(score_data['dimension'])
                        score = CriticScore(
                            dimension=dimension,
                            score=float(score_data['score']),
                            reasoning=score_data.get('reasoning', ''),
                            suggestions=score_data.get('suggestions', [])
                        )
                        dimension_scores.append(score)
                    except (ValueError, KeyError) as e:
                        logger.warning(f"解析维度评分失败:{e}")
                        continue
            
            # 提取其他字段
            overall_score = float(data.get('overall_score', 7.0))
            summary_critique = data.get('summary_critique', '批判解析失败')
            suggestions = data.get('improvement_suggestions', [])
            
            return dimension_scores, overall_score, summary_critique, suggestions
            
        except Exception as e:
            logger.error(f"批判结果解析失败:{e}")
            # 返回默认结果
            return self._get_default_critique_result()
    
    def _get_default_critique_result(self) -> Tuple[List[CriticScore], float, str, List[str]]:
        """获取默认批判结果"""
        default_scores = []
        for dimension in CriticDimension:
            score = CriticScore(
                dimension=dimension,
                score=7.0,
                reasoning=f"默认{dimension.value}评分",
                suggestions=[f"改进{dimension.value}相关方面"]
            )
            default_scores.append(score)
        
        return (
            default_scores,
            7.0,
            "批判分析过程出现问题,使用默认评分",
            ["建议重新进行详细分析", "优化内容质量", "加强专业性"]
        )
    
    def _calculate_satisfaction_score(self, 
                                    previous_critiques: Optional[List[CriticOutput]],
                                    current_scores: List[CriticScore]) -> float:
        """计算满意度评分 (Satisfaction score)"""
        if not previous_critiques or not current_scores:
            return 7.0  # 默认满意度
        
        try:
            # 获取最近的批判结果
            last_critique = previous_critiques[-1]
            
            # 计算各维度的改进程度
            improvements = []
            for current_score in current_scores:
                # 查找对应维度的历史评分
                for last_score in last_critique.dimension_scores:
                    if last_score.dimension == current_score.dimension:
                        improvement = current_score.score - last_score.score
                        improvements.append(improvement)
                        break
            
            if improvements:
                # 计算平均改进程度
                avg_improvement = sum(improvements) / len(improvements)
                # 转换为满意度评分 (0-10)
                satisfaction = 7.0 + avg_improvement  # 基准7分 + 改进程度
                return max(0.0, min(10.0, satisfaction))  # 限制在0-10范围内
            
            return 7.0
            
        except Exception as e:
            logger.warning(f"满意度评分计算失败:{e}")
            return 7.0
    
    async def batch_critique(self, 
                           actor_outputs: List[ActorOutput],
                           critic_agents: List[Agent], 
                           task: Task) -> List[CriticOutput]:
        """批量批判多个Actor输出"""
        logger.info(f"开始批量批判,输出数量:{len(actor_outputs)},批判者数量:{len(critic_agents)}")
        
        # 为每个Actor输出分配批判者（可以是多对多关系）
        critique_tasks = []
        for actor_output in actor_outputs:
            for critic_agent in critic_agents:
                # 避免自我批判
                if actor_output.agent_id != critic_agent.agent_id:
                    critique_tasks.append(
                        self.critique_output(actor_output, critic_agent, task)
                    )
        
        # 并发执行所有批判任务
        critique_results = await asyncio.gather(*critique_tasks, return_exceptions=True)
        
        # 处理结果
        valid_critiques = []
        for result in critique_results:
            if isinstance(result, Exception):
                logger.error(f"批判任务失败:{result}")
                continue
            valid_critiques.append(result)
        
        logger.info(f"批量批判完成,成功:{len(valid_critiques)}/{len(critique_tasks)}")
        return valid_critiques
    
    def get_critique_statistics(self) -> Dict[str, Any]:
        """获取批判统计信息"""
        if not self.critique_history:
            return {
                'total_critiques': 0,
                'average_overall_score': 0,
                'average_satisfaction_score': 0,
                'current_iteration': self.current_iteration,
                'api_available': self.naga_conversation is not None
            }
        
        total_overall = sum(c.overall_score for c in self.critique_history)
        total_satisfaction = sum(c.satisfaction_score for c in self.critique_history)
        successful_critiques = [c for c in self.critique_history if not c.metadata.get('error', False)]
        
        return {
            'total_critiques': len(self.critique_history),
            'successful_critiques': len(successful_critiques),
            'failed_critiques': len(self.critique_history) - len(successful_critiques),
            'average_overall_score': total_overall / len(self.critique_history),
            'average_satisfaction_score': total_satisfaction / len(self.critique_history),
            'current_iteration': self.current_iteration,
            'api_available': self.naga_conversation is not None,
            'average_critique_time': sum(c.critique_time for c in self.critique_history) / len(self.critique_history)
        }
    
    def get_latest_critique(self) -> Optional[CriticOutput]:
        """获取最新的批判结果"""
        return self.critique_history[-1] if self.critique_history else None
    
    def clear_history(self):
        """清空批判历史"""
        self.critique_history.clear()
        self.current_iteration = 0
        logger.info("Criticizer批判历史已清空") 
 