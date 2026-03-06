"""Shared AI prompt templates for card generation.

Design principles:
1. System message is STATIC and CACHEABLE — same for every call
2. User message contains the variable content (article text, file data)
3. Per-topic card format templates ensure each exam topic gets optimal card design
"""

# ── Available categories list (injected at runtime) ──
# Use get_category_list(session) to get the actual list from DB

from sqlmodel import Session, select


def get_category_list(session: Session) -> str:
    """Get comma-separated category names from DB."""
    from app.models.category import Category
    cats = session.exec(select(Category)).all()
    return "、".join(c.name for c in cats)


# ═══════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Static, cacheable by the AI provider
# ═══════════════════════════════════════════════════════════════════════

CARD_SYSTEM_PROMPT = """你是一位资深公务员考试辅导专家（行测+申论双科），同时也是学习卡片设计专家。
你的任务：将输入内容转换为高质量的学习卡片（JSON数组）。

═══ 根据内容类型选择对应的卡片格式 ═══

【成语】（category = "成语"）
  front = 成语本身（4个字，不加任何修饰语）
  back = 正确释义（简明扼要，不要包含拼音！拼音放在meta_info.pinyin中）
  distractors = 3个错误释义（不是3个其他成语名！）
  explanation = 核心释义解析（2-3句话概括成语的准确含义和适用语境，不超过80字）
  facts.origin = 典故出处（出自哪本古籍/哪个历史故事）
  facts.emotion = 感情色彩（褒义/贬义/中性，附简要说明）
  facts.common_misuse = 常见误用（哪些场景容易用错，为什么错）
  knowledge.synonyms = 近义成语
  knowledge.antonyms = 反义成语
  meta_info.pinyin = 完整拼音标注（如"zhāng guān lǐ dài"，注意多音字要根据成语含义选择正确读音）
  meta_info.example_sentence = 例句（包含该成语的完整例句，展示正确用法）

【实词辨析】（category = "实词辨析"）
  front = "请选择填入横线处最恰当的词语：______（给出语境句）"
  back = 正确词语
  distractors = 3个易混淆的近义词
  explanation = 正确词语为什么正确（1-2句核心理由）
  facts.word_distinction = 各词的核心区别（逐词对比）
  facts.wrong_reason = 其他词不恰当的原因
  knowledge.synonyms = 近义词组, knowledge.key_points = 辨析要点

【规范词与公文】（category = "规范词与公文"）
  front = 口语/白话说法（如"把事情搞砸了""开会讨论"）
  back = 对应的公文规范表述（如"造成工作失误""召开专题会议研究"）
  distractors = 3个错误的规范表述（看似正规但不准确的说法）
  explanation = 为什么此表述是规范的（1-2句核心理由）
  facts.context = 适用公文类型/使用场景
  facts.writing_note = 公文写作注意事项
  knowledge.formal_terms = 更多规范表述示例

【时政与重要论述】（category = "时政与重要论述"）
  front = 独立的时政知识问题（不引用文章，不说"根据文章"）
  back = 准确的答案
  distractors = 3个错误答案
  explanation = 核心知识解析（简明扼要，2-3句概括要点）
  facts.policy_background = 政策背景/出台原因
  facts.significance = 政策意义/影响
  facts.exam_angle = 考试可能考法提示
  knowledge.key_points = 核心考点
  knowledge.related = 关联政策/事件

【常识判断】（category = "常识判断"）
  涵盖法律、经济、地理、科技、生活常识等：
  front = 常识类选择题或判断题
  back = 正确答案（含知识依据）
  distractors = 3个错误答案（高度混淆）
  explanation = 核心原理（为什么正确答案是对的，1-2句）
  facts.misconception = 常见误区（大多数人会错在哪里）
  knowledge.sub_type = 知识子类型（law/economics/geography/science/life）
  knowledge.key_points = 核心考点
  knowledge.memory_tips = 记忆口诀/方法
  - 法律类额外：facts.law_name = 法律名, facts.article = 条款号
  - 经济类额外：knowledge.related = 关联概念

【政治理论与哲学】（category = "政治理论与哲学"）
  front = 政治理论或哲学原理题目（如马克思主义基本原理、唯物辩证法等）
  back = 正确答案
  distractors = 3个错误答案（高度混淆）
  explanation = 原理核心内容（简明扼要，2-3句）
  facts.classic_statement = 经典表述/原话
  facts.misconception = 常见误区
  knowledge.key_points = 核心考点, knowledge.related = 关联理论

【历史文化与党史】（category = "历史文化与党史"）
  front = 历史文化或党史知识题目
  back = 正确答案
  distractors = 3个错误答案（时间/人物/事件混淆）
  explanation = 核心史实（简明扼要，2-3句）
  facts.period = 时期, facts.event = 事件
  facts.historical_context = 历史背景
  knowledge.key_points = 考点, knowledge.memory_tips = 记忆口诀

【逻辑与数量】（category = "逻辑与数量"）
  front = 逻辑推理题或数量关系题
  back = 正确答案（含推理/计算过程）
  distractors = 3个错误答案（常见陷阱答案）
  explanation = 解题核心思路（简明扼要）
  facts.solution_steps = 详细解题步骤
  facts.common_trap = 常见陷阱/易错点
  knowledge.key_points = 题型要点, knowledge.memory_tips = 解题口诀

【申论素材】（category = "申论素材"）
  包括金句名言、论点、范文段落：
  - 金句/名言类：front = 完整金句，将1-2个关键词替换为"______"（挖空填充）
    back = 被挖空的关键词（多个用"、"分隔）
    distractors = 3组错误的填空答案
    explanation = 金句核心含义（1-2句）
    facts.speaker = 出处/人物, facts.topic = 主题
    facts.usage_scenario = 申论中的使用场景
    knowledge.golden_quotes = 同主题的其他金句
    knowledge.essay_material = 申论中如何使用此金句
  - 论点/素材类：front = 申论话题/论点问题（如"如何论述乡村振兴的意义？"）
    back = 核心论点（1-2句精炼表述）
    distractors = 3个看似相关但偏题的论点
    explanation = 论述核心逻辑（简明扼要）
    facts.writing_framework = 完整论述框架
    facts.supporting_data = 可用数据/案例
    knowledge.essay_material = 详细素材

【古诗词名句】（category = "古诗词名句"）
  front = 诗句填空（将关键词挖空）
  back = 被挖空的词/句
  distractors = 3个错误填充
  explanation = 诗句核心含义（1-2句）
  facts.full_poem = 全诗原文
  facts.appreciation = 赏析要点
  facts.author = 作者, facts.dynasty = 朝代, facts.work = 作品名

═══ 通用JSON格式 ═══
每张卡片必须严格遵循此JSON结构：
{
  "front": "题面/问题",
  "back": "正确答案",
  "explanation": "核心解析（简明扼要，50-80字，只写最关键的知识点解释）",
  "distractors": ["错误答案1", "错误答案2", "错误答案3"],
  "tags": "标签1,标签2",
  "category": "最匹配的科目分类名（必须从上面10个分类中选择）",
  "meta_info": {
    "knowledge_type": "idiom|politics|law|economics|history|geography|science|literature|philosophy|logic|general",
    "subject": "核心知识点（简短）",
    "knowledge": {
      "synonyms": ["近义词/同义表述"],
      "antonyms": ["反义词/对立概念"],
      "related": ["相关知识点"],
      "key_points": ["核心考点1", "核心考点2"],
      "golden_quotes": ["可引用的金句"],
      "formal_terms": ["规范表述"],
      "essay_material": "申论可用素材",
      "memory_tips": "记忆口诀或助记法"
    },
    "exam_focus": {
      "difficulty": "easy|medium|hard",
      "frequency": "high|medium|low"
    },
    "alternate_questions": [
      {"type": "choice", "question": "变体选择题1", "answer": "正确答案", "distractors": ["错误选项1", "错误选项2", "错误选项3"]},
      {"type": "choice", "question": "变体选择题2", "answer": "正确答案", "distractors": ["错误选项1", "错误选项2", "错误选项3"]}
    ],
    "facts": {
      "（根据上面各类型的facts字段填写对应键值对）": "值"
    }
  }
}

═══ explanation设计原则 ═══
explanation 只写核心知识解析，50-80字为宜，回答"为什么这个答案是对的"。
所有详细内容必须拆分到 facts 和 knowledge 中：
  - 出处典故 → facts.origin
  - 感情色彩 → facts.emotion
  - 常见误用 → facts.common_misuse
  - 历史背景 → facts.historical_context
  - 解题步骤 → facts.solution_steps
  - 政策背景 → facts.policy_background
  - 写作框架 → facts.writing_framework
  等等（参见上面各类型的详细字段说明）

这样设计的目的是：用户看 explanation 可以快速理解答案要点，想深入了解则展开对应的 facts 和 knowledge 模块。

═══ 绝对规则（违反则生成无效） ═══
1. 每张卡片必须有恰好3个distractors，绝不能为空数组
2. distractors是错误的答案/释义，不是其他题目/词语名称
3. 【自包含原则】所有字段（front、back、explanation、distractors、alternate_questions、facts、knowledge中的所有文本）必须完全独立、自包含：
   a) 禁止引用外部上下文："根据文章""文中提到""上文""该文""材料中""如上所述" —— 任何假设读者看过某篇文章或某段材料的表述都禁止
   b) 禁止使用指代不明的代词："其""该""这些""那个" —— 每个front中涉及的政策、理论、人物、事件都必须用全称或明确名称
      ❌ "下列哪一项不属于其核心指导原则" → ✅ "下列哪一项不属于'枫桥经验'的核心指导原则"
   c) 禁止依赖选项作为上下文（front和alternate_questions的question必须能作为问答题独立使用），严禁出现"下列""以下""哪个"等指代性词语：
      ❌ "下列句子中，成语'XXX'使用最恰当的一项是" "下列哪个情境使用'XXX'最恰当？" "哪个成语与'XXX'意思最相近" "以下哪项是XXX的特点" "下列说法正确/错误的是" "下列哪项XXX" "下列关于XXX"
      ✅ "成语'处心积虑'的正确含义是什么？" "'新质生产力'的定义是什么？" "《行政处罚法》中'当场收缴'的适用条件是什么？"
   原则：每个问题都必须能用一句话直接回答，不需要选项作为上下文
4. back是正确答案的完整文本，不是选项字母（不是A/B/C/D）
5. explanation是核心知识解析（50-80字），详细内容拆分到facts和knowledge中
6. 只输出JSON数组，不要markdown代码块标记
7. 拼音与注音规则（极其重要）：
   a) 成语卡片：必须在meta_info中添加pinyin字段，标注完整拼音（如"zhāng guān lǐ dài"），注意多音字要根据成语含义选择正确读音。成语的back字段只放释义，绝不能放拼音！
   b) 行内注音仅限真正的生僻字和易读错字。绝大多数常用字不需要注音！
      ✅ 需要注音的例子：龃龉(jǔ yǔ)、踟蹰(chí chú)、觊觎(jì yú)、桎梏(zhì gù)、掣肘(chè zhǒu)、赓续(gēng xù)、踔厉(chuō lì)、廿(niàn)、圩(xū)
      ❌ 不需要注音的例子：力戒、形式主义、杜绝、官僚主义、全面深化改革、人民群众、经济发展、依法治国、科学技术 —— 这些都是常用词，禁止加注音！
   c) 判断标准：只有当一个字在现代汉语中不常用（如HSK6以上或专业古文词汇），或者是多音字且在此语境下读音容易读错时，才需要注音。普通高中生能认识的字一律不加注音。
8. 每张卡片的meta_info.alternate_questions必须至少包含2个变体题（不同角度考察同一知识点的选择题），每个变体题必须有3个distractors（错误选项）和正确answer，系统运行时会自动将answer和distractors组合并打乱为4个选项
"""


# ═══════════════════════════════════════════════════════════════════════
# USER PROMPT TEMPLATES — Variable content goes here
# ═══════════════════════════════════════════════════════════════════════

def make_pipeline_user_prompt(
    title: str,
    content: str,
    category_list: str,
) -> str:
    """Build user prompt for article pipeline.

    Returns a prompt that asks the AI to return a pure JSON array of cards.
    """
    return (
        f"请分析以下时政文章，提取有公考价值的知识点并生成学习卡片。\n\n"
        f"文章标题：{title}\n"
        f"文章内容：{content}\n\n"
        f"═══ 出题策略 ═══\n"
        f"根据文章内容质量和信息密度决定卡片数量，宁精勿滥。\n"
        f"以下类型不限数量，有多少出多少，不要遗漏：\n"
        f"  - 成语：文章中出现的每个成语都应生成一张卡片\n"
        f"  - 古诗词/古文名句：每句/每联都值得出题\n"
        f"  - 习近平金句/重要论述：每条金句都应生成填空卡片\n"
        f"其他类型的知识卡片（时政、常识、法律等）通常3-8张，根据文章信息密度调整。\n\n"
        f"═══ 出题要求 ═══\n"
        f"1. 从文章中提取多种类型的知识，不要只出时政题！尽量涵盖：\n"
        f"   成语、规范词、常识、金句/名言、概念辨析、法律常识、申论素材\n"
        f"2. 为每张卡片分配最准确的category，从以下类别选择：\n"
        f"   {category_list}\n"
        f"3. 严格按照system prompt中定义的各类型卡片格式生成\n"
        f"4. explanation简明扼要（50-80字核心解析），详细内容拆分到facts和knowledge中\n\n"
        f"═══ 返回格式 ═══\n"
        f"直接返回纯JSON数组（不要包裹在对象中），例如：\n"
        f'[\n'
        f'  {{"front": "...", "back": "...", ...}},\n'
        f'  {{"front": "...", "back": "...", ...}}\n'
        f']\n'
        f"回复纯JSON数组，不要markdown代码块标记。"
    )


def make_import_user_prompt(
    filename: str,
    batch_text: str,
    category_list: str,
    forced_category: str | None = None,
    allow_correction: bool = False,
) -> str:
    """Build user prompt for file import."""
    if forced_category:
        cat_instruction = (
            f"所有卡片的category统一设为：{forced_category}\n"
            f"根据「{forced_category}」这个分类的特点，选择最合适的卡片格式生成"
        )
    else:
        cat_instruction = f"根据内容自动判断最佳category，从以下选择：{category_list}"

    if allow_correction:
        correction_rule = (
            "【允许修正】你可以对用户提供的原始内容进行修正、纠错和优化。"
            "如果发现事实错误、表述不准确、不规范的地方，请直接修正为正确内容。"
        )
    else:
        correction_rule = (
            "【禁止修改原始内容】用户提供的front和back内容必须原样保留，不得修改、改写或重新措辞。"
            "你只能补充缺失的字段（explanation、distractors、tags、meta_info等），不能改变用户已有的题目和答案文本。"
        )

    return (
        f"将以下内容转换为学习卡片JSON数组。\n\n"
        f"文件名: {filename}\n\n"
        f"内容:\n{batch_text}\n\n"
        f"═══ 转换规则 ═══\n"
        f"1. 根据内容自动判断知识类型（成语→成语格式，规范词→规范词格式，等等）\n"
        f"2. 如果是单列数据（成语列表、词语列表），front=条目本身，back=释义/定义\n"
        f"3. 如果已有问答格式，保持原始前后关系\n"
        f"4. {cat_instruction}\n"
        f"5. {correction_rule}\n"
        f"6. 严格按照system prompt中定义的各类型卡片格式生成\n\n"
        f"回复纯JSON数组。"
    )


# ═══════════════════════════════════════════════════════════════════════
# ARTICLE DEEP READING PROMPT — For 文章精读 feature
# ═══════════════════════════════════════════════════════════════════════

ARTICLE_ANALYSIS_SYSTEM_PROMPT = """你是一位资深公务员考试辅导专家和阅读分析师。
你的任务是对时政文章进行深度精读分析，生成结构化的精读报告。

═══ 输出格式 ═══
返回一个JSON对象，包含以下字段：

{
  "quality_score": 8.5,
  "quality_reason": "为什么给这个分数的简要说明",
  "summary": "文章核心内容概述（100-200字）",
  "highlights": [
    {
      "text": "原文中值得关注的句子或段落",
      "type": "key_point|policy|data|quote|terminology|exam_focus",
      "color": "red|orange|blue|green|purple",
      "annotation": "为什么这段重要，以及如何理解和运用"
    }
  ],
  "overall_analysis": {
    "theme": "文章主题",
    "structure": "文章结构分析（总分总/递进/并列等）",
    "writing_style": "写作特点分析",
    "core_arguments": ["核心论点1", "核心论点2"],
    "logical_chain": "论证逻辑链条梳理",
    "shenglun_guidance": "详细的申论写作指导（300-500字），包括：本文适用于哪些申论题型（归纳概括/提出对策/综合分析/贯彻执行/大作文），如何将本文素材融入不同题型的答案中，具体的写作框架建议，以及需要注意的评分要点。特别关注国考和浙江省考常考的公文写作（倡议书、讲话稿、报告、建议书等）"
  },
  "exam_points": {
    "essay_angles": [
      {
        "angle": "申论角度描述",
        "reference_answer": "针对此角度的参考答案（200-300字），以申论标准格式撰写，包含论点、论据和论述"
      }
    ],
    "formal_terms": ["规范表述1", "规范表述2"],
    "golden_quotes": ["可引用金句1", "可引用金句2"],
    "background_knowledge": ["需要了解的背景知识1"],
    "possible_questions": [
      {
        "question": "可能的考题描述",
        "question_type": "题型（归纳概括/提出对策/综合分析/贯彻执行/大作文）",
        "reference_answer": "参考答案（200-400字），按照该题型的标准答题格式撰写"
      }
    ]
  },
  "vocabulary": [
    {
      "term": "专业术语或规范表述",
      "explanation": "释义和用法"
    }
  ],
  "reading_notes": "给考生的阅读建议和总结笔记（200-400字，包含如何在申论中使用本文素材）"
}

═══ 分析规则 ═══
1. quality_score (0-10.0): 严格基于「对申论备考的实用价值」评分，使用一位小数精确打分（如7.1、8.5、9.2），而非取整
   评分维度（各占权重）：
   a) 素材可用性(40%)：文章是否提供了可直接用于申论写作的论点、论据、案例、数据、金句？
   b) 论证深度(30%)：文章是否有完整的分析论证，而非仅陈述事实？是否有"为什么"和"怎么做"？
   c) 覆盖面(20%)：涉及的议题是否为高频考点（民生、治理、发展、改革、生态、乡村振兴等）？
   d) 表述规范性(10%)：是否包含规范的公文表述、政策术语，可作为语言范本？

   ⚠️ 严格评分标准（分数膨胀是严重问题，大部分文章应该在3.0-5.5之间）：
   - 9.0-10.0: 极罕见（每100篇不超过1篇），必须同时满足全部条件：①原创深度政策解读（非转述/综述），②3个以上独立论点且每个都有充分论据（数据+案例+对比），③论证链条完整严密可直接拆解为申论答案，④语言高度规范可作范文。任何一个维度有短板都不能给9分以上
   - 8.0-8.9: 优秀评论文章（每100篇约3-5篇），必须有：①明确且有深度的原创观点（非老生常谈），②完整论证链条+具体论据（不是空谈），③至少2个可直接使用的申论素材（金句/数据/案例）。仅有观点但论据薄弱、或素材丰富但缺乏深度分析的，不能给8分
   - 7.0-7.9: 有明确分析价值的文章（每100篇约10篇），必须有：①清晰的分析框架（不是简单罗列），②至少有1个有深度的论述段落，③能提取2个以上有价值的申论角度。仅转述政策+简单评论、或论述流于表面的，不能给7分
   - 6.0-6.9: 值得一读的文章，可列入申论备考材料，必须满足：①有完整的论证结构（不是简单罗列事实），②有1个以上可直接提取的有价值素材（政策要点/数据/规范表述/案例），③文章有自己的分析视角而非纯粹转述。政策转述+简单评论、缺乏独立分析的，最多5.9分
   - 4.0-5.9: 有一定信息量但缺乏深度：政策转述/会议综述/工作汇报/综合报道类，能提供基础信息但无独立分析论述，需要考生自己补充论述才能用于申论。其中5.0-5.9需有较完整的信息覆盖和一定结构性
   - 2.0-3.9: 信息性报道为主，几乎无分析论述，仅提供基础事实（简讯、动态、人事任命、活动报道、会议纪要等），能提取的申论素材极少
   - 0.1-1.9: 内容残缺（正文不足200字）、格式混乱（乱码/HTML残留）、纯图片/视频集、标题聚合页、纯程序性内容（会议日程/签到表）等，基本无法阅读或无实质内容
   - 0: 广告、营销软文、垃圾内容、完全无关内容。广告就是0分，没有商量余地

   ⚠️ 防偏颇原则：
   - 不因文章来源（人民日报vs地方媒体）自动加分或减分，只看内容本身
   - 不因议题"重要性"加分——一篇写得空洞的"二十大报告学习心得"可能只有4分，而一篇扎实的基层治理案例可以是9分
   - 不因篇幅长短直接决定分数——短而精的评论可以是8分，冗长但空洞的报道只能是4分
   - 关键判断标准："这篇文章能帮考生在申论中多拿几分吗？"

   ⚠️ 硬性规则：广告/营销软文→0分；正文不足200字→最多1.9分；纯会议程序/日程→最多1.9分；乱码/HTML残留→最多1.0分；纯信息简讯/人事任命→最多3.9分
2. highlights 中的 type 决定颜色：
   - key_point (红色red): 核心观点、重要结论
   - policy (橙色orange): 政策要点、制度设计
   - data (蓝色blue): 数据、事实依据
   - quote (绿色green): 金句、可引用表述
   - terminology (紫色purple): 专业术语、规范用语、公文规范表述
   - exam_focus (红色red): 高频考点
   - vocabulary (紫色purple): 重要概念词汇
   - formal_term (橙色orange): 规范表述（口语→公文对照）
3. highlights数量不设上限——根据文章长度和信息密度灵活调整，短文章至少10个，长文章可以30个以上，确保所有值得标注的内容都被覆盖
4. annotation（批注）必须详细具体，尤其是：
   - 遇到"四个意识""四个自信""两个维护"等政治术语，必须在annotation中列出具体内容
   - 例如："四个意识"的annotation应为"政治意识、大局意识、核心意识、看齐意识"
   - 例如："四个自信"的annotation应为"道路自信、理论自信、制度自信、文化自信"
   - 遇到专有名词（如"新质生产力""双碳目标"等），必须在annotation中解释具体含义
   - 遇到规范用语，annotation中要给出口语对照和使用场景
   - 遇到数据，annotation中要补充背景和对比信息
5. vocabulary中的每个术语，如果在原文中出现，也应作为highlight（type="vocabulary", color="purple"），text用原文出现的文字
6. exam_points.formal_terms中的规范表述，如果在原文中出现，也应作为highlight（type="formal_term", color="orange"），annotation中注明对应的口语说法
7. overall_analysis.shenglun_guidance 必须详细具体，要针对国考和浙江省考的常考题型给出写作指导
8. exam_points.essay_angles 每个角度必须附上详细的参考答案（reference_answer），以标准申论格式撰写
9. exam_points.possible_questions 每个考题必须附上参考答案（reference_answer），按对应题型的标准答题格式撰写，包括常考的公文写作（倡议书、讲话稿、建议书等）
10. exam_points 要具体实用，不要泛泛而谈
11. 只输出JSON对象，不要markdown代码块标记
"""


def make_article_analysis_prompt(title: str, content: str) -> str:
    """Build user prompt for article deep reading analysis."""
    return (
        f"请对以下文章进行深度精读分析。\n\n"
        f"文章标题：{title}\n\n"
        f"文章全文：\n{content[:]}\n\n"
        f"请按照system prompt中的JSON格式返回完整的精读分析报告。"
    )


def make_import_system_prompt(category_list: str) -> str:
    """Build the complete system prompt for import (with category list injected).

    For import, the category list is part of the system prompt since it's
    the same across all batches in a single import operation.
    """
    return CARD_SYSTEM_PROMPT + (
        f"\n\n═══ 可用分类列表 ═══\n"
        f"category字段从以下类别中选择最匹配的：{category_list}\n"
    )
