# -*- coding: utf-8 -*-
"""
industry.py - 场景3：行业报告。AI 结合业务数据库政策与新闻，生成高颜值深度行业分析报告。
"""

import os
import json
from openai import OpenAI
from utils.mock_db import INDUSTRIES
from utils.file_helper import ensure_dir, send_to_webhook
import utils.db_helper as db

ALL_26_INDUSTRIES = [
    {
        "title": "一、 人工智能：生成式大模型与智能体生态的商业化深度落地",
        "content": """【行业整体发展概述】2026年人工智能行业正式进入商业化落地与端侧应用爆发期，智能体工作流（Agentic Workflows）与基座大模型生态深度耦合。
【重大事件一：上海基座模型在 OpenRouter 智能体调用量榜单包揽前三】
• 事件：开源 AI 智能体框架 Hermes Agent（“爱马仕”）登顶 OpenRouter 智能体调用量榜首后，OpenRouter 平台智能体调用量前三名全部由上海基座模型包揽：第一名阶跃星辰 Step 3.5 Flash、第二名稀宇科技 MiniMax M2.5、第三名蚂蚁百灵 Ling-2.6-1T。
• 关键企业：稀宇科技（MiniMax）、阶跃星辰（Step）、蚂蚁百灵（蚂蚁集团）。
• 信号意义：上海基座大模型在“智能体调用”这一实战指标上已进入全球第一梯队，体现出极强的开源生态和工程化落地能力。
【重大事件二：大模型“五小龙”估值与二级市场股价集体暴涨，上海生态深度耦合】
• 事件：2026年5月中旬，国内大模型头部公司股价与估值出现集体暴涨。MiniMax 股价大涨 18.46%，市值约 2566 亿港元，发布 MiniMax M2.7 并推出基于 Hermes Agent 的自进化 AI 助手；阶跃星辰完成近 25 亿美元融资，产业链资本（华勤、龙旗、豪威、中兴）参与；月之暗面（Kimi）完成 D 轮 20 亿美元融资，投后估值突破 200 亿美元。
• 上海角色：MiniMax 总部在上海；阶跃星辰、月之暗面在沪有核心研发和算力生态布局，与上海本地芯片及云服务深度耦合。"""
    },
    {
        "title": "二、 半导体芯片：先进封装技术与关键设备国产化攻坚",
        "content": """【行业整体发展概述】2026年半导体芯片行业处于三维多芯片堆叠先进封装与国产 EDA 全流程工具先进制程适配大面积普及的关键突破阶段。
【重大事件一：CoWoS与Chiplet先进封装产能瓶颈全面破局】
• 事件：随着大算力 GPU 和高带宽内存（HBM）需求持续高涨，国内主流封装企业在2026年Q1完成了先进封装产线的二期扩产，全球先进封装总产能同比提升70%，有效缓解了高算力芯片的短缺。
• 关键企业：长电科技、通富微电、华天科技。
• 信号意义：先进封装产能的释放，为国内算力芯片的交付提供了强有力的供应链保障。
【重大事件二：国产一站式全流程 EDA 软件实现 3nm 先进制程适配】
• 事件：国内头部 EDA 厂商成功推出针对 3nm 及以下先进制程 of 数模混合和数字后端流片全流程工具，并在国内主流晶圆厂通过验证，流片良率达到 85% 以上。
• 关键企业：华大九天、概伦电子。
• 信号意义：标志着国内设计厂商在高端芯片设计环节基本摆脱了国外巨头的封锁，国产替代率大幅提高。"""
    },
    {
        "title": "三、 新新能源产业：光伏风电效能提升与多元化储能技术并进",
        "content": """【行业整体发展概述】新能源产业由粗放式装机向高效能并网与多元化化学储能转变，全固态电池试点与钙钛矿叠层技术取得里程碑进展。
【重大事件一：全球首条 G 瓦级全固态锂电池生产线在上海示范运行】
• 事件：2026年3月，国内首个 G 瓦级全固态电池生产基地正式投产，其量产电芯能量密度突破 500 Wh/kg，并在高安全性和循环寿命上展现出革命性提升。
• 关键企业：宁德时代、清陶能源、上汽集团。
• 信号意义：标志着全固态动力电池迈入商业化量产前夜，有望彻底重塑新能源汽车动力格局。
【重大事件二：钙钛矿/晶硅叠层光伏电池商业效率突破 33%】
• 事件：2026年5月，国内光伏厂商研制的钙钛矿叠层电池商业组件在户外实证中效率突破 33%，面积化组件量产效率达到 28.5% 的新纪录。
• 关键企业：隆基绿能、通威股份。
• 信号意义：进一步降低度电成本（LCOE），加速光伏产业向平价上网与新型电力系统构建转型。"""
    },
    {
        "title": "四、 医疗行业：智慧医疗与临床诊疗的数字化转型",
        "content": """【行业整体发展概述】医疗行业聚焦于智慧医院建设、跨院健康大数据互联互通以及基于生成式 AI 的远程辅助诊疗系统的普惠化应用。
【重大事件一：国家级健康大数据平台与电子病历跨省互认体系建成】
• 事件：2026年首季度，全国跨省份电子病历互认互免平台正式上线，减少了 25% 以上的重复检查率，有效盘活了全国综合医疗资源。
• 关键企业：卫宁健康、东华软件。
• 信号意义：提升了基层群众就医的便利度，标志着医疗信息化改革走向深水区。
【重大事件二：AI 智能诊疗助手在全国 5000 家基层医院常态化部署】
• 事件：基于大模型的医学影像识别和辅助处方系统全面接入乡镇卫生院，使多发病和慢性病的早期筛查准确率提高到 95% 以上。
• 关键企业：科大讯飞、百度健康。
• 信号意义：大幅缓解了基层医疗资源匮乏的痛点，实现了优质医疗资源的普惠化沉淀。"""
    },
    {
        "title": "五、 消费品牌：DTC模式深化与全渠道数字生态建设",
        "content": """【行业整体发展概述】消费品牌深度重构全渠道数字生态，以数据驱动的 DTC（直面消费者）模式和柔性敏捷供应链成为核心壁垒。
【重大事件一：主流消费品牌数字化供应链改造渗透率突破 65%】
• 事件：2026年，通过大数据预测流行趋势，多品牌实现了“小单快反”的柔性生产，其库存周转天数（ITO）平均缩短 15 天。
• 关键企业：安踏集团、百丽时尚。
• 信号意义：降低了库存积压和资金占用成本，重构了消费品牌的利润分配模式。
【重大事件二：AR 沉浸式零售与虚拟穿戴实现全渠道商用】
• 事件：主流运动与美妆品牌相继推出 3D 试鞋及 AI智能彩妆镜，线上试用转化率提升了 38%。
• 关键企业：美图公司、得物。
• 信号意义：线上线下消费场景加速交融，为消费者带来了全新的沉浸式体验。"""
    },
    {
        "title": "六、 智能机器人：具身智能与人形机器人的产业化落地",
        "content": """【行业整体发展概述】智能机器人行业正经历从“传统自动化”向“具身智能”的跃迁，人形机器人开始进入主流工厂并开启规模化实训。
【重大事件一：上海眸深智能（Motion Brain）完成 3 亿元 Pre-A 轮融资】
• 事件：2026年5月，专注“生成式跨本体通用具身大脑”的上海眸深智能宣布完成 3 亿元 Pre-A 轮融资，投资方包括绿技行资本、闽招基金、利欧股份等。
• 核心技术：提出“世界动作模型”（World Motion Model），发布 MotionGPT、HL3DWM 三维世界模型，强调端侧部署与持续学习能力。
• 产业落地：已与宇树科技、小米集团等达成合作，并与极具示范效应的养老机构签署万台康养机器人战略合作。
【重大事件二：国家级具身智能机器人创新中心发布“天枢”大模型2.0】
• 事件：2026年Q1，创新中心推出了专为机器人控制设计的具身大模型2.0，对复杂未知环境的泛化理解成功率提升至92%。
• 关键企业：优必选、傅利叶智能。
• 信号意义：大幅降低了大制造场景的示教时间，实现了人形机器人在工业装配线上的手眼精细协同操作。"""
    },
    {
        "title": "七、 生物医药领域：靶向疗法创新与临床转化速度加快",
        "content": """【行业整体发展概述】生物医药领域聚焦于抗体偶联药物（ADC）、细胞与基因疗法（CGT）的创新研发，国内药企在出海和融资上取得重大突破。
【重大事件一：剂泰科技与英派药业港股上市，上海科创基金迎里程碑】
• 事件：2026年5月，AI 驱动纳米材料创新与药物递送的“剂泰科技”与专注合成致死抗癌创新药的“英派药业”同日在港交所挂牌上市，首日收盘涨幅均翻倍。
• 关键基金：上海科创基金（目标规模 300 亿元，已投资子基金超 100 支，已上市企业达 202 家）。
• 上海生态：两家公司深度融入张江药谷生态，上海科创基金作为国资母基金是其核心出资方。
【重大事件二：达歌生物（Degron Therapeutics）完成 A 轮扩展融资 4000 万美元】
• 事件：临床阶段生物技术公司达歌生物宣布完成 4000 万美元 A 轮扩展融资，由龙磐资本领投，高特佳投资、石药国方先导基金等参投。
• 技术管线：核心项目 DEG6498 为 First-in-Class HuR 分子胶降解剂，已在晚期实体瘤患者中开展 I 期临床。
• 上海关联：公司由上海科技大学教授仓勇创立，总部设在上海，是典型的高校科研转化标杆。"""
    },
    {
        "title": "八、 集成电路领域：高端芯片设计与设计工具（EDA）突破",
        "content": """【行业整体发展概述】集成电路行业聚焦于大算力芯片、高带宽内存（HBM）的自主研发与先进制程芯片的规模化量产。
【重大事件一：国产大容量 HBM3E 内存芯片量产线试产成功】
• 事件：2026年5月，国内首条具备自主知识产权的高带宽内存堆叠线完成全线调试，大幅缓解了人工智能算力对高端内存的进口依赖。
• 关键企业：长鑫存储、中芯国际。
• 信号意义：打通了高端 AI 加速卡的核心存储瓶颈，强化了本土芯片的配套硬实力。
【重大事件二：车规级自动驾驶 MCU 及传感器芯片国产替代率突破 70%】
• 事件：国内主流整车厂加速采用自研或本土车规级控制芯片，产业链上下游国产适配度大幅增强。
• 关键企业：地平线、芯驰科技。
• 信号意义：形成了稳定的车规级本土供应链循环，降低了供应链中断风险。"""
    },
    {
        "title": "九、 空天经济：低空空域开放与商业卫星互联网布局",
        "content": """【行业整体发展概述】空天经济在政策红利下迎来爆发式增长，低空空域管理系统的数字化和商业卫星互联网星座组网速度显著加快。
【重大事件一：低空空中交通管理系统（UTM）在长三角三省一市率先试点】
• 事件：2026年，低空飞行数字化空域图正式发布，城市物流无人机及eVTOL（电动垂直起降航空器）完成了超十万架次的飞行安全测试。
• 关键企业：亿航智能、峰飞航空。
• 信号意义：推动低空经济由“单点试飞”向“网格化商业运营”迈进。
【重大事件二：商业航天“千帆星座”实现批量化一箭多星发射常态化】
• 事件：2026年上半年，低轨互联网卫星星座完成多批次轨道部署，在轨卫星数突破500颗。
• 关键企业：垣信卫星、蓝箭航天。
• 信号意义：实现了全球无缝空天窄带通信覆盖，提升了我国在低轨空间轨道的国际竞争力。"""
    },
    {
        "title": "十、 数字经济领域：数据要素资产化与“数实融合”走深走实",
        "content": """【行业整体发展概述】数字经济成为推动产业转型升级的主引擎，数据要素确权入表机制逐步完善，“数实融合”在各行各业走深走实。
【重大事件一：多省发放首批“数据资产权属登记凭证”】
• 事件：2026年，数据资产入表及评估准则在全国范围正式推开，数十家企业将持有的核心数据资产进行合规登记，开辟了企业融资新渠道。
• 关键企业：上海数据交易所、易华录。
• 信号意义：推动了数据要素资产化进程，释放了沉睡数据资产的真实金融价值。
【重大事件二：工业互联网标识解析体系国家顶级节点日均解析量超 20 亿次】
• 事件：标识解析技术在汽车、装备等重点行业供应链追踪中普及，实现了全国跨区域物联数据的高效连接。
• 关键企业：东方国信、卡奥斯。
• 信号意义：奠定了数字孪生工厂和智慧供应链的数据底座。"""
    },
    {
        "title": "十一、 人工智能领域：算力基础设施建设与绿色低碳智算中心",
        "content": """【行业整体发展概述】2026年，人工智能领域大模型算力需求呈现指数级爆发，促使智算中心向大规模集群、超低能耗液冷和分布式算网调度协同方向深度发展。
【重大事件一：顺网科技与华为联合发布“全光毫秒算网”解决方案】
• 事件：2026年5月14日，顺网科技与华为共同举办“全光毫秒算网”算力服务解决方案发布会，主题为“光算协同以智赋网”，正式在沪落地分布式算力网络。
• 关键企业：顺网科技、华为。
• 信号意义：实现了算力资源的广域调度与毫秒级极低时延响应，显著降低了企业获取高性能大算力的物理门槛，加速了边缘算力与中心算力的协同应用。
【重大事件二：“九章四号”可编程光量子计算原型机研制成功】
• 事件：2026年5月，中科大潘建伟、陆朝阳团队联合上海人工智能实验室等单位成功研制出可编程光量子计算原型机“九章四号”，在高斯玻色取样问题上比当前全球最快超级计算机快10^54倍，刷新光量子计算世界纪录。
• 关键机构：上海人工智能实验室、中国科学技术大学。
• 信号意义：在大模型智算之外，前沿物理算力及量子融合AI方向取得关键突破，对上海量子计算与AI算力生态具有显著放大效应。"""
    },
    {
        "title": "十二、 战新综合领域：战略性新兴产业集群与产业链韧性建设",
        "content": """【行业整体发展概述】战略性新兴产业综合领域以补链强链、产业链韧性与跨区域集群协同为核心导向，重点推进硬科技投融资与出海数字供应链服务体系建设。
【重大事件一：张江高科参设上海科创中心二期基金，募集规模达 80 亿元】
• 事件：2026年5月中旬，张江高科公告拟认缴出资 2 亿元参设“上海科创中心二期私募投资基金”，该基金整体规模达 80 亿元，主要投向集成电路、生物医药、人工智能等上海三大先导产业。
• 关键企业：张江高科、上海科创集团。
• 信号意义：通过国资母基金撬动社会资本，放大了对早中期硬科技项目的资本供给，为硬科技生态提供了坚实的资金安全垫。
【重大事件二：中佰云科完成 1.5 亿元 A 轮融资，助力出海供应链服务】
• 事件：2026年5月14日，总部位于上海的跨境电商全景解决方案提供商“中佰云科”宣布完成 1.5 亿元人民币 A 轮融资，投资方为云南资本。
• 关键企业：中佰云科。
• 信号意义：体现了上海在“跨境支付+供应链金融+出海服务”赛道上强大的资源集聚与资本吸纳力，促进实体战新企业向全球化延伸。"""
    },
    {
        "title": "十三、 装备制造：高端数控机床与重大装备的智能化升级",
        "content": """【行业整体发展概述】装备制造业正加快向高端化、高精度化迈进。五轴联动数控机床、重型燃气轮机和工业母机核心零部件国产化及系统集成率稳步攀升。
【重大事件一：国产大容量重型燃气轮机实现核心热端部件100%自主制造】
• 事件：2026年，自主研发的重型燃气轮机示范工程成功点火并网，其高温合金转子与第一级静叶均实现国产自主设计制造。
• 关键企业：上海电气、东方电气。
• 信号意义：彻底打破了国外巨头在重型燃机关键热端部件上的长期技术封锁，标志着我国大容量重型动力装备制造取得里程碑突破。
【重大事件二：五轴联动高精度数控机床全球出口量同比增长45%】
• 事件：国内机床龙头企业在精密导轨、直驱电主轴等核心部件上实现全国产化替代，高精度五轴机床大批量出口欧洲及东南亚中高端制造市场。
• 关键企业：沈阳机床、科德数控。
• 信号意义：反映出我国数控系统和高端机床不仅满足国内产业升级需求，且在国际中高端市场具备了更强的出口竞争力。"""
    },
    {
        "title": "十四、 时尚消费品：传统工艺与数字时尚的交融发展",
        "content": """【行业整体发展概述】时尚消费品行业通过深度融入3D虚拟设计、AI潮流趋势预测与数字化柔性供应链，实现了极高效率的“小单快反”柔性化生产。
【重大事件一：2026中国上海 VR/AR 产业博览会展示“AI+XR”消费融合创新】
• 事件：2026年5月14-15日，博览会在上海跨国采购会展中心成功举行，小派科技等厂商在现场展示了 2700 万像素超清头显等“AI+XR”终端与内容生态。
• 关键企业：小派科技、得物。
• 信号意义：体现了上海在虚拟穿戴与沉浸式零售场景上的技术积聚效应，展示出线上线下消费场景交融的巨大商业转化潜力。
【重大事件二：主流时尚消费品牌数字化供应链改造渗透率突破 65%】
• 事件：2026年，通过大数据预测流行趋势，多品牌实现了柔性生产，其库存周转天数（ITO）平均缩短 15 天；同时利用海洋垃圾和生物基聚酯纤维替代传统化纤，低碳环保材料使用比例突破 30%。
• 关键企业：安踏集团、百丽时尚。
• 信号意义：降低了库存积压与资金占用成本，实现了消费品牌降本增效与零碳环保双向转型的绿色增长。"""
    },
    {
        "title": "十五、 新材料：特种合金与前沿碳纤维 of 研发及应用",
        "content": """【行业整体发展概述】新材料作为战略先导产业的基石，目前以特种合金、前沿碳纤维的万吨级量产及 AI for Science（AI4S）智能材料计算平台的突破为发展重点。
【重大事件一：复鞍智能完成数千万元种子轮融资，推出 LASPAI 智能材料计算平台】
• 事件：2026年5月14日，专注 AI for Science（AI4S）在物质科学领域应用的“复鞍智能”宣布完成数千万元种子轮融资，该企业由复旦大学化学系刘智攀教授团队发起。
• 核心产品：LASPAI 智能材料计算平台，能将原子级模拟与智能计算引入材料与化学研发，将传统数周计算时间压缩至秒级。
• 信号意义：极大加速了新能源、半导体及催化剂材料的研发试错流程，成为以人工智能驱动新材料研发的校企科研转化典型。
【重大事件二：T1000级超高强碳纤维万吨级生产线全线满负荷投产】
• 事件：2026年，国产高模量高强度碳纤维在航天及大飞机 C919/C929 机体制造中实现规模化应用，万吨级产线全线满负荷稳定运转。
• 关键企业：中复神鹰、光威复材。
• 信号意义：解决了民用航空与高端航天轻量化材料的国产化问题，支撑大飞机机体国产率进一步提升。"""
    },
    {
        "title": "十六、 航天：深空探测任务推进与运载火箭回收商业化",
        "content": """【行业整体发展概述】航天领域在2026年继续保持高频发射态势，商业航天力量迅速崛起，卫星星座的大量部署与液体火箭的垂直回收成为商业化核心。
【重大事件一：商业航天“千帆星座”实现批量化一箭多星发射常态化】
• 事件：2026年上半年，低轨互联网卫星星座完成多批次轨道部署，在轨卫星数成功突破 500 颗，实现了全球无缝空天窄带通信覆盖。
• 关键企业：垣信卫星、蓝箭航天。
• 信号意义：表明商业卫星制造与规模化组网进入工业化量产轨道，空天经济全球通信能力显著增强。
【重大事件二：国产百吨级可重复使用液体运载火箭成功完成垂直回收试验】
• 事件：2026年5月，新型可重复火箭在长三角及西北基地顺利完成百公里级高空发射并精准垂直降落在指定平台，单次发射成本下降 60% 以上。
• 关键企业：蓝箭航天、深蓝航天。
• 信号意义：大幅降低了商业卫星拼网的轨道部署成本，加速了我国低轨卫星网星座建设的全球竞争力。"""
    },
    {
        "title": "十七、 核电：三代核电技术规模化与第四代反应堆技术引领",
        "content": """【行业整体发展概述】核电作为绿色低碳的基荷能源，建设步伐稳健。以三代“华龙一号”的规模化并网与四代高温气冷堆的安全商业运行为核心标志。
【重大事件一：全球首个第四代商业化高温气冷堆实现安全运行突破1000天】
• 事件：2026年，位于石岛湾的第四代商业化高温气冷堆核电站示范工程实现持续满负荷安全运行超1000天，核心非能动安全特性在实战中通过检验。
• 关键企业：华能集团、中核集团、清华大学。
• 信号意义：标志着第四代反应堆不仅具备极高安全性，且其热电联产效率与高温工艺热输出全面具备商业化推广价值。
【重大事件二：“华龙一号”第四批机组相继在东部沿海核电基地并网发电】
• 事件：2026年上半年，新一批三代核电“华龙一号”机组在福建、广东等沿海基地陆续投入商业运行，单台机组年均提供低碳清洁电量超100亿度。
• 关键企业：中国核电、中广核。
• 信号意义：有效平抑了东部沿海工业大省的基荷电力缺口，单台机组年均减排二氧化碳超800万吨。"""
    },
    {
        "title": "十八、 生物医药：新药创制 and 医疗器械国产化替代",
        "content": """【行业整体发展概述】生物医药行业在2026年聚焦高精尖临床诊断设备的国产化替代与上海本地生物医药高质量发展专项政策的落实。
【重大事件一：上海市发布“生物医药创新发展”项目申报指南与促进政策】
• 事件：2026年5月12日，上海市科委发布2026年度科技产业高质量发展计划“生物医药创新发展”项目申报指南（沪科指南〔2026〕5号），重点资助“靶点发现”等子专题，单个项目资助额度达200万元。
• 关键园区：张江药谷、临港生命蓝湾等园区内的创新药企获直接政策红利。
• 信号意义：以政策扶持鼓励企业与科研院所进行首创靶点发掘，推动我国原创新药研发加速由仿创（Me-too）向首创（First-in-class）跃升。
【重大事件二：恒瑞医药子公司 RSS0393 乳膏临床试验获批，丰富新药管线】
• 事件：2026年5月14日，恒瑞医药子公司瑞石生物收到国家药监局核准签发的《药物临床试验批准通知书》，同意开展 RSS0393 乳膏用于特应性皮炎治疗的临床试验。
• 关键企业：恒瑞医药（连云港上市，上海设有研发中心）、瑞石生物。
• 信号意义：展现出龙头药企在自身免疫/皮肤疾病领域的长效布局，上海的研发与临床中心是其全球新药创制的核心节点。"""
    },
    {
        "title": "十九、 电子信息：超高清显示技术与物联网端侧芯片普及",
        "content": """【行业整体发展概述】电子信息产业作为国民经济战略支柱，聚焦 Micro-LED 柔性显示器件的商业量产与端侧 AIoT 无源芯片的产业化应用。
【重大事件一：昆仑芯天池 256 卡超节点正式点亮，大算力硬件完成生态适配】
• 事件：2026年5月中旬，昆仑芯 P800 在国内多个万卡智算集群中完成规模化验证，其“天池 256 卡超节点”正式点亮，适配文心、DeepSeek、GLM、MiniMax 等主流大模型，推理效率提升 50%。
• 关键企业：昆仑芯片。
• 信号意义：国内大算力加速芯片在大规模异构算力集群中完成工程化闭环，为云端 AI 大模型提供强大的国产硬算力支撑。
【重大事件二：首条商业化 Micro-LED 微显示屏量产线实现良率 88% 的关键突破】
• 事件：2026年，国内新型显示巨头研制的 AR/VR 智能眼镜专用 Micro-LED 微显示芯片良率迈过商业化门槛，月产能突破百万片级别。
• 关键企业：京东方、华星光电。
• 信号意义：攻克了微显示器件在亮度与功耗之间的核心技术瓶颈，开启了超轻便 AR 眼镜等消费电子新硬件的爆发期。"""
    },
    {
        "title": "二十、 钢铁：绿色低碳冶金工艺与高端特种钢材研发",
        "content": """【行业整体发展概述】钢铁行业在“双碳”目标下，加速由传统高能耗冶炼向氢冶金、电炉短流程及极端环境特种钢材制造转型。
【重大事件一：百万吨级超大型“氢气替代焦炭”冶金示范项目全面达产】
• 事件：2026年，国内首条百万吨级氢冶金工艺产线实现平稳运行，通过使用氢气作为还原剂代替传统焦炭，吨钢二氧化碳排放减少了 65% 以上。
• 关键企业：宝武钢铁、河钢集团。
• 信号意义：标志着我国钢铁冶炼工艺实现了划时代的绿色变革，为高排放、高污染的冶金重工业开辟了实质性的碳达峰路径。
【重大事件二：国产耐极寒特种极地船舶钢板在大型破冰船中大范围装船】
• 事件：2026年初，由国内特钢集团研制的极地级船体钢板通过全球四大船级社认证，在我国新一代极地破冰科考船中实现 100% 国产化搭载，可承受零下 60 摄氏度极端严寒冲击。
• 关键企业：沙钢集团、鞍钢集团。
• 信号意义：攻克了极寒恶劣环境下钢材易发生脆性断裂的技术难题，提升了我国极地工程与高附加值特种船型制造的自主性。"""
    },
    {
        "title": "二十一、 汽车：新能源汽车渗透率攀升与智能网联汽车商用",
        "content": """【行业整体发展概述】新能源汽车市场渗透率持续稳定在50%以上的高位，固态动力电池迈入商业量产前夜，高阶自动驾驶（L3/L4）迎来商业化准入落地。
【重大事件一：国家智能网联汽车高阶自动驾驶（L3/L4）示范运行牌照在 30 城发放】
• 事件：2026年5月，工业和信息化部等部门正式向国内首批试点车企颁发 L3/L4 级自动驾驶商业化运营牌照，在全国 30 个核心城市开启常态化高阶自动驾驶路测与收费。
• 关键企业：上汽集团、广汽集团、百度 Apollo。
• 信号意义：标志着城市 NOA（导航辅助驾驶）从“辅助驾驶”真正跨入“责任托管”阶段，开启了智能网联汽车的下半场竞争。
【重大事件二：全国高速服务区超快充（800V高压/4C以上）覆盖率突破 85%】
• 事件：2026年，国家能源局与电网企业联合推进的“超充高速路网”计划实施，使得纯电动汽车在高速公路实现“充电 5 分钟，续航 300 公里”的高效补能体验。
• 关键企业：国家电网、特来电。
• 信号意义：彻底打破了新能源汽车长途出行的充电时间焦虑，推动新能源车全场景普及与渗透率进一步攀升。"""
    },
    {
        "title": "二十二、 建筑：装配式建筑推广与建筑信息模型（BIM）应用",
        "content": """【行业整体发展概述】建筑行业正从现场湿作业向预制装配、绿色低碳及工程数字化转型，重型交通枢纽基建项目的智能化装配式施工水平创下新高。
【重大事件一：上海东站枢纽工程完成巨型钢结构屋盖整体提升，创国内同类站房新纪录】
• 事件：2026年5月14日，上海东站枢纽工程顺利完成 7.4 万平方米、约 9000 吨巨型钢结构屋盖的整体提升（高度 13.5 米），采用“地面整体拼装+智能协同提升”工艺。
• 关键技术：使用 56 台泵站及 178 个专用油缸进行智能泵网协同，729 项监测数据实时上传。
• 信号意义：该项目应用了全寿命周期 BIM 仿真与智能群控调配，将提升误差控制在毫米级，展现出我国在智能建造与重型装配式施工领域的全球顶尖水平。
【重大事件二：新建住宅建筑装配式施工面积比例强制规范出台，智能化机器人常态化部署】
• 事件：2026年，各一二线城市出台新建住宅项目装配式比例不低于 40% 的刚性约束，同时粉刷新墙机、砌砖机器人等在保障房项目中的普及率达 25%。
• 关键企业：碧桂园（博智林）、上海建工。
• 信号意义：显著减少了施工粉尘与现场噪音污染，工期进度提升近 30%，大大缓解了建筑行业人口红利消退后的劳动力结构压力。"""
    },
    {
        "title": "二十三、 能源：多能互补系统建设与智慧能源管理网络",
        "content": """【行业整体发展概述】能源系统加速构建清洁低碳、多能互补的新型电力系统。化石能源清洁高效利用与大规模新能源并网的虚拟电厂平抑成为发展重心。
【重大事件一：华北区域跨省虚拟电厂智能调度平台响应能力突破千万千瓦】
• 事件：2026年，通过将数十万个分布式储能、充电桩与工商业柔性空调负荷进行云端聚合，国内首个超大规模虚拟电厂实现秒级负荷削峰填谷。
• 关键企业：国家电网、南网科技。
• 信号意义：为大规模间歇性风电与光伏并网提供了灵活动态平抑机制，显著降低了电网因新能源并网产生的崩塌风险。
【重大事件二：十万吨级原油开采 CCUS（二氧化碳捕集、利用与封存）示范项目全面投产】
• 事件：2026年，该示范工程通过回收工业废气中的二氧化碳高压注入油藏进行驱油，采收率提升 15%，同时实现了二氧化碳在地下深处的永久物理封存。
• 关键企业：中国石化、宝武钢铁。
• 信号意义：实现了二氧化碳排放的闭环循环与资源化再利用，开辟了高耗能工业与化石能源开采协同降碳的全新路径。"""
    },
    {
        "title": "二十四、 船舶：绿色动力船舶订单爆发与高附加值船型突围",
        "content": """【行业整体发展概述】船舶工业迎来绿色甲醇及氨燃料双动力船舶的全球订单爆发期，大型豪华邮轮及超大型集装箱船建造效率领跑全球。
【重大事件一：全球首批 1.5 万 TEU 甲醇双燃料集装箱船在上海批量交付】
• 事件：2026年5月，由江南造船厂和沪东中华等船企联合建造的全球首批 1.5 万箱甲醇双燃料集装箱船顺利交付，温室气体排放较燃油船下降 90%。
• 关键企业：中国船舶（江南造船、沪东中华）。
• 信号意义：我国在绿色清洁能源动力系统、双耳储罐等核心技术上拥有完整自主知识产权，标志着高附加值绿色动力船型进入成熟商业收割期。
【重大事件二：国产第二艘大型豪华邮轮顺利出坞下水并开启试航】
• 事件：2026年上半年，国产第二艘大型豪华邮轮在上海正式出坞，其总装建造效率和核心舾装国产化率比首艘“爱达·魔都号”提升了 25% 以上。
• 关键企业：外高桥造船。
• 信号意义：标志着我国在中高端造船领域实现了客滚船、豪华邮轮的大规模建造能力跨越，确立了全球造船业“皇冠明珠”的量产底蕴。"""
    },
    {
        "title": "二十五、 航空：国产大飞机产业化运营与民用航空产业链协同",
        "content": """【行业整体发展概述】以商飞 C919 的常态化规模化商业运营为契机，国产民用航空产业链的国产化配套能力逐步增强，宽体机 C929 稳步推进。
【重大事件一：国产大飞机 C919 累计商业载客量突破 100 万人次，签派可靠度超 99%】
• 事件：2026年5月，东航等三大航司运营的 C919 机队累计载客突破百万人次大关，在沪深、沪京等黄金航线稳定运行，签派可靠度指标达到国际主流客机水平。
• 关键企业：中国商飞、中国东航。
• 信号意义：说明国产窄体客机在安全运行、日常维护和商业载客上完成了商业运营的闭环实证，全面转入规模化交付。
【重大事件二：新一代宽体大客机 C929 正式进入机体总装与航空电子联合调试阶段】
• 事件：2026年上半年，针对大飞机重大科研专项，C929 宽体客机完成了全机身复合材料机翼强度及主要飞控软件在实验室联合验证，开始首架样机机体组装。
• 关键企业：中国商飞。
• 信号意义：大飞机研制体系由单通道向双通道宽体客机跨越，大幅提升了我国在全球大型民用客机研制领域的战略主导地位。"""
    },
    {
        "title": "二十六、 水务：智慧水务精细化运营与水资源循环利用",
        "content": """【行业整体发展概述】水务行业通过传感器、物联网与数字孪生水网的深度融合，大幅度降低管网漏损，海水淡化实现高性能国产膜组件的突破。
【重大事件一：城市级“数字孪生智慧水网系统”上线，漏损率降至 6% 以下】
• 事件：2026年，国内多个特大型城市完成了地下管网的数字孪生数字化升级，通过部署数十万个智能流量及压力监测点，实现微小渗漏毫米级定位。
• 关键企业：上海城投水务、大禹节水。
• 信号意义：将管网漏损率降至 6%（远优于国家标准），大幅减少了宝贵的城市淡水资源浪费，奠定了新型智慧城市低碳供水底座。
【重大事件二：万吨级沿海超大型反渗透海水淡化示范厂并网，国产反渗透膜组件量产应用】
• 事件：2026年，采用国产高性能大面积反渗透膜组件的海水淡化厂在长三角及北方沿海平稳运行，日产淡水超 10 万立方米，吨水生产电耗同比降低 20%。
• 关键企业：沃顿科技、碧水源。
• 信号意义：标志着海水淡化核心高性能膜材料彻底打破外资技术垄断，在保障沿海临港工业区及海岛用水安全上拥有自主可控的技术护城河。"""
    }
]


def md_to_html(text: str) -> str:
    if not text:
        return ""
    import re
    # Convert headers
    text = re.sub(r'###\s+(.*?)(?:\n|$)', r'<h3>\1</h3>', text)
    text = re.sub(r'####\s+(.*?)(?:\n|$)', r'<h4>\1</h4>', text)
    # Convert bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    
    # Handle lists
    lines = text.split('\n')
    new_lines = []
    in_ul = False
    in_ol = False
    
    for line in lines:
        ul_match = re.match(r'^\s*[-*]\s+(.*)', line)
        ol_match = re.match(r'^\s*\d+\.\s+(.*)', line)
        
        if ul_match:
            if in_ol:
                new_lines.append('</ol>')
                in_ol = False
            if not in_ul:
                new_lines.append('<ul>')
                in_ul = True
            new_lines.append(f'<li>{ul_match.group(1)}</li>')
        elif ol_match:
            if in_ul:
                new_lines.append('</ul>')
                in_ul = False
            if not in_ol:
                new_lines.append('<ol>')
                in_ol = True
            new_lines.append(f'<li>{ol_match.group(1)}</li>')
        else:
            if in_ul:
                new_lines.append('</ul>')
                in_ul = False
            if in_ol:
                new_lines.append('</ol>')
                in_ol = False
            stripped = line.strip()
            if stripped:
                new_lines.append(line)
            else:
                new_lines.append('')
                
    if in_ul:
        new_lines.append('</ul>')
    if in_ol:
        new_lines.append('</ol>')
        
    result_lines = []
    for line in new_lines:
        if line.strip() in ['<ul>', '</ul>', '<ol>', '</ol>', '<li>', '</li>', '<h3>', '</h3>', '<h4>', '</h4>']:
            result_lines.append(line)
        elif line.strip() == '':
            result_lines.append('<br/>')
        else:
            result_lines.append(line + '<br/>')
            
    html = '\n'.join(result_lines)
    html = re.sub(r'(<br/>\s*)+', '<br/>', html)
    if html.endswith('<br/>'):
        html = html[:-5]
    return html

def generate_html_report(dest_path: str, title: str, summary: str, chapters: list, policies: list = None, weiban_policies: list = None, news: list = None) -> str:
    """
    生成高颜值的 A4 排版 HTML 报告，集成打印功能，展示真实政策与新闻，避免中文字体乱码问题。
    """
    from datetime import datetime
    chapters_html = ""
    for ch in chapters:
        ch_title = ch.get("title", "")
        ch_content = md_to_html(ch.get("content", ""))
        chapters_html += f"""
        <div class="chapter">
            <h2>{ch_title}</h2>
            <div class="chapter-content">{ch_content}</div>
        </div>
        """

    # 构建政策动态 HTML
    policies_html = ""
    if policies:
        for p in policies:
            p_title = p.get("标题") or "无标题"
            p_unit = p.get("发布单位") or "未知单位"
            p_time = p.get("发布时间") or "未知时间"
            p_url = p.get("网址") or "#"
            policies_html += f"""
            <div class="intel-item">
                <div class="intel-title">{p_title}</div>
                <div class="intel-meta">
                    <span>🏢 {p_unit}</span>
                    <span>📅 {p_time}</span>
                </div>
                <div><a href="{p_url}" target="_blank" class="intel-link">查看原件 ➔</a></div>
            </div>
            """
    else:
        policies_html = "<div class='intel-item' style='color:#64748b;font-style:italic;'>暂无国家政策公告</div>"

    # 构建委办局地方政策 HTML
    weiban_html = ""
    if weiban_policies:
        for p in weiban_policies:
            p_title = p.get("标题") or "无标题"
            p_unit = p.get("发布单位") or "未知单位"
            p_time = p.get("发布时间") or "未知时间"
            p_url = p.get("网址") or "#"
            weiban_html += f"""
            <div class="intel-item">
                <div class="intel-title">{p_title}</div>
                <div class="intel-meta">
                    <span>🏛️ {p_unit}</span>
                    <span>📅 {p_time}</span>
                </div>
                <div><a href="{p_url}" target="_blank" class="intel-link">查看原件 ➔</a></div>
            </div>
            """
    else:
        weiban_html = "<div class='intel-item' style='color:#64748b;font-style:italic;'>暂无地方委办局政策</div>"

    # 构建新闻动态 HTML
    news_html = ""
    if news:
        for n in news:
            n_title = n.get("标题") or "无标题"
            n_source = n.get("来源") or "未知来源"
            n_date = n.get("发布日期") or "未知日期"
            n_url = n.get("URL") or "#"
            news_html += f"""
            <div class="intel-item">
                <div class="intel-title">{n_title}</div>
                <div class="intel-meta">
                    <span>📰 {n_source}</span>
                    <span>📅 {n_date}</span>
                </div>
                <div><a href="{n_url}" target="_blank" class="intel-link">阅读全文 ➔</a></div>
            </div>
            """
    else:
        news_html = "<div class='intel-item' style='color:#64748b;font-style:italic;'>暂无实时新闻动态</div>"

    html_content = f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js"></script>
    <style>
        :root {{
            --primary: #0f172a;
            --primary-dark: #020617;
            --secondary: #1e3a8a;
            --accent: #2563eb;
            --accent-gold: #eab308;
            --text-main: #334155;
            --text-dark: #0f172a;
            --bg-light: #f8fafc;
            --border-color: #e2e8f0;
        }}
        body {{
            font-family: 'Outfit', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: var(--text-main);
            background-color: var(--bg-light);
            line-height: 1.8;
            margin: 0;
            padding: 40px 20px;
        }}
        .report-card {{
            max-width: 840px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 50px 60px;
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05);
        }}
        
        /* 封面样式 */
        .cover-page {{
            background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
            color: #ffffff;
            padding: 60px 40px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
            position: relative;
            overflow: hidden;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
        }}
        .cover-page::before {{
            content: "";
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 60%);
            pointer-events: none;
        }}
        .cover-tag {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: var(--accent-gold);
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 20px;
        }}
        .cover-title {{
            font-size: 30px;
            font-weight: 700;
            line-height: 1.4;
            margin: 0 0 20px 0;
            color: #ffffff;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }}
        .cover-subtitle {{
            font-size: 15px;
            color: #94a3b8;
            margin-bottom: 30px;
        }}
        .cover-meta {{
            display: flex;
            justify-content: center;
            gap: 24px;
            font-size: 13px;
            color: #cbd5e1;
            border-top: 1px solid rgba(255, 255, 255, 0.15);
            padding-top: 20px;
            margin-top: 20px;
        }}
        
        /* 前言导读样式 */
        .summary-box {{
            background-color: #f8fafc;
            border-left: 4px solid var(--accent);
            padding: 24px;
            border-radius: 8px;
            margin-bottom: 30px;
            font-size: 15px;
            color: var(--text-dark);
            border: 1px solid var(--border-color);
            border-left-width: 4px;
        }}
        .summary-box h3 {{
            margin: 0 0 12px 0;
            color: var(--secondary);
            font-size: 16px;
            font-weight: 700;
        }}
        
        /* 分页线样式 */
        .page-break {{
            border-bottom: 2px dashed var(--border-color);
            margin: 40px 0;
            position: relative;
        }}
        .page-break::after {{
            content: "分页标记 (仅在导出PDF时自动截断分页)";
            position: absolute;
            top: -11px;
            right: 20px;
            background: #ffffff;
            padding: 0 10px;
            font-size: 11px;
            color: #94a3b8;
        }}
        
        /* 章节正文样式 */
        .chapter {{
            margin-bottom: 40px;
        }}
        .chapter h2 {{
            font-size: 18px;
            color: var(--secondary);
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 8px;
            margin-top: 0;
            margin-bottom: 18px;
            font-weight: 700;
        }}
        .chapter-content {{
            font-size: 14.5px;
            text-align: justify;
            color: var(--text-main);
            line-height: 1.8;
        }}
        
        /* Markdown 解析排版样式 */
        .chapter-content h3 {{
            font-size: 16px;
            color: var(--text-dark);
            margin-top: 20px;
            margin-bottom: 10px;
            font-weight: 600;
        }}
        .chapter-content h4 {{
            font-size: 15px;
            color: var(--text-dark);
            margin-top: 15px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .chapter-content strong {{
            color: var(--text-dark);
        }}
        .chapter-content ul {{
            list-style: none;
            padding-left: 20px;
            margin: 12px 0;
        }}
        .chapter-content ul li {{
            position: relative;
            margin-bottom: 8px;
            padding-left: 4px;
        }}
        .chapter-content ul li::before {{
            content: "◆";
            position: absolute;
            left: -16px;
            color: var(--accent);
            font-size: 10px;
            top: 0px;
        }}
        .chapter-content ol {{
            padding-left: 20px;
            margin: 12px 0;
        }}
        .chapter-content ol li {{
            margin-bottom: 8px;
        }}
        
        /* 实时产业情报样式 */
        .intelligence-section {{
            margin-top: 50px;
            border-top: 2px dashed var(--border-color);
            padding-top: 35px;
            page-break-inside: avoid;
        }}
        .intelligence-section h2 {{
            font-size: 18px;
            color: var(--secondary);
            margin-bottom: 24px;
            font-weight: 700;
        }}
        .intelligence-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 1024px) {{
            .intelligence-grid {{
                grid-template-columns: 1fr 1fr;
            }}
        }}
        @media (max-width: 768px) {{
            .intelligence-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        .intelligence-card {{
            background: #f8fafc;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            page-break-inside: avoid;
        }}
        .intelligence-card h3 {{
            margin-top: 0;
            margin-bottom: 15px;
            font-size: 15px;
            color: var(--text-dark);
            border-left: 3px solid var(--accent);
            padding-left: 8px;
            font-weight: 700;
        }}
        .intel-item {{
            font-size: 13px;
            margin-bottom: 12px;
            border-bottom: 1px solid #f1f5f9;
            padding-bottom: 10px;
            page-break-inside: avoid;
        }}
        .intel-item:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        .intel-title {{
            font-weight: 600;
            color: var(--text-dark);
            margin-bottom: 4px;
            line-height: 1.4;
        }}
        .intel-meta {{
            color: #64748b;
            font-size: 11px;
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
            margin-top: 4px;
        }}
        .intel-link {{
            color: var(--accent);
            text-decoration: none;
            font-weight: 600;
        }}
        .intel-link:hover {{
            text-decoration: underline;
        }}
        
        .footer {{
            margin-top: 50px;
            border-top: 1px solid var(--border-color);
            padding-top: 20px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
        }}
        
        .actions-bar {{
            max-width: 840px;
            margin: 0 auto 20px auto;
            display: flex;
            justify-content: flex-end;
        }}
        .btn {{
            background: linear-gradient(135deg, var(--accent) 0%, var(--secondary) 100%);
            color: white;
            border: none;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2);
        }}
        .btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 6px 12px rgba(37, 99, 235, 0.3);
        }}
        
        @media print {{
            body {{
                background-color: white;
                padding: 0;
                color: black;
            }}
            .report-card {{
                border: none;
                box-shadow: none;
                padding: 0;
                max-width: 100%;
            }}
            .no-print {{
                display: none !important;
            }}
            @page {{
                size: A4;
                margin: 20mm;
            }}
            .page-break {{
                border: none;
                margin: 0;
                height: 0;
                page-break-after: always;
            }}
            .page-break::after {{
                display: none;
            }}
            .chapter h2, .intelligence-section h2, .intelligence-card h3 {{
                page-break-after: avoid;
            }}
            .chapter {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="actions-bar no-print">
        <button class="btn" onclick="downloadPDF()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
            保存 PDF 至本地
        </button>
    </div>
    
    <div class="report-card">
        <div class="first-page">
            <div class="cover-page">
                <div class="cover-tag">INDUSTRY DEPTH RESEARCH REPORT</div>
                <h1 class="cover-title">{title}</h1>
                <div class="cover-subtitle">AI智能体客户洞察项目组 | 行业深度研究报告</div>
                <div class="cover-meta">
                    <span>📅 生成时间: {datetime.now().strftime('%Y-%m-%d')}</span>
                    <span>🛡️ 机密级别: 内部参考</span>
                </div>
            </div>
            
            <div class="summary-box">
                <h3>前言导读</h3>
                <p>{summary}</p>
            </div>
        </div>
        
        <div class="page-break"></div>
        
        {chapters_html}

        <!-- 实时产业情报数据源展示 -->
        <div class="intelligence-section">
            <h2>🔗 实时产业情报数据源 (多源数据融合接入)</h2>
            <div class="intelligence-grid">
                <div class="intelligence-card">
                    <h3>📋 国家与行业政策</h3>
                    {policies_html}
                </div>
                <div class="intelligence-card">
                    <h3>🏛️ 地方委办局政策</h3>
                    {weiban_html}
                </div>
                <div class="intelligence-card">
                    <h3>📰 产业新闻与动态</h3>
                    {news_html}
                </div>
            </div>
        </div>
        
        <div class="footer">
            © {datetime.now().year} AI智能体客户洞察项目组 | 本报告由大模型辅助生成，仅供决策参考
        </div>
    </div>
    <script>
        function downloadPDF() {{
            const element = document.querySelector('.report-card');
            const opt = {{
                margin:       15,
                filename:     '{title}.pdf',
                image:        {{ type: 'jpeg', quality: 0.98 }},
                html2canvas:  {{ scale: 2, useCORS: true }},
                jsPDF:        {{ unit: 'mm', format: 'a4', orientation: 'portrait' }}
            }};
            html2pdf().set(opt).from(element).save();
        }}
    </script>
</body>
</html>
"""
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return dest_path


def handle(keyword: str, user_id: int = None) -> dict:
    """
    生成行业深度报告 HTML，并自动推送至机器人 Webhook。返回报告访问链接。
    """
    k = str(keyword or "").strip()
    
    regions_list = [
        "浦东新区", "黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区",
        "闵行区", "宝山区", "嘉定区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区",
        "浦东", "黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明",
        "上海", "上海市", "全市", "全区", "区域", "全市行业", "全市所有行业"
    ]
    if k in regions_list:
        k = "全行业"
        keyword = "全行业"
        
    if not k or (k in ("行业", "行业报告", "生成行业报告", "行业研报") or ("行业报告" in k and "全行业" not in k)):
        return {
            "type": "text",
            "content": "请问您需要生成哪个行业的深度分析报告？（例如：人工智能、医药、新能源，或回复“全行业”生成汇编报告）"
        }

    # 如果关键词是空，或是泛指的“全行业”、“行业”、“行业报告”、“生成行业报告”等，均判定为全行业汇编报告
    is_all_industries = (
        "全行业" in k
    )
    
    if is_all_industries:
        keyword = "全行业"
    
    # 查找匹配的行业数据 (做兜底)
    industry_data = None
    matched_key = None
    
    if not is_all_industries:
        for k, v in INDUSTRIES.items():
            if keyword in k or k in keyword:
                industry_data = v
                matched_key = k
                break
            
    is_dynamic = False
    if is_all_industries:
        matched_key = "全行业"
        title = "2026年中国全行业前沿趋势与商业洞察汇编报告"
        summary = "本报告对中国26个战略先导与支柱产业进行全面梳理，结合当前宏观政策与实时产业新闻动态，深度呈现各行业的发展现状与未来商业契机。"
        chapters = ALL_26_INDUSTRIES
    elif not industry_data:
        is_dynamic = True
        matched_key = keyword
        # 若是未录入的行业，设定默认值（以通信行业作备用大纲，大模型未启动或异常时会退化使用）
        backup_data = INDUSTRIES["通信行业"]
        title = backup_data["title"]
        summary = backup_data["summary"]
        chapters = backup_data["chapters"]
    else:
        title = industry_data["title"]
        summary = industry_data["summary"]
        chapters = industry_data["chapters"]
        
    db.log_event(user_id, "industry", "INFO", f"开始为行业 '{matched_key}' (动态生成: {is_dynamic}, 全行业汇编: {is_all_industries}) 生成 HTML 深度分析报告。")
    
    policies = []
    weiban_policies = []
    news = []
    articles = []
    
    # 1. 从业务库中动态查询最新政策与上海新闻 (均从 weixin_deepseek_extract_d 统一获取)
    if is_all_industries:
        try:
            # A. 检索微信去重公众号文章库 (weixin_deepseek_extract_d) - 画像核心文本源
            articles_sql = """
                SELECT `article_title` AS `title`, `article_content` AS `content`, `article_url` AS `link`, `publish_time` AS `date`, `wechat_name` AS `name`
                FROM weixin_deepseek_extract_d 
                ORDER BY `publish_time` DESC LIMIT 5
            """
            articles = db.query_business_db(articles_sql)
            db.log_event(user_id, "industry", "INFO", f"全行业查询微信动态表成功，获得 {len(articles)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"全行业微信文章查询异常: {e}")

        try:
            policies_sql = """
                SELECT `article_title` AS `标题`, `article_content` AS `正文`, `article_url` AS `网址`, `wechat_name` AS `发布单位`, `publish_time` AS `发布时间` 
                FROM weixin_deepseek_extract_d 
                WHERE `article_title` LIKE '%政策%' OR `article_title` LIKE '%通知%' OR `article_title` LIKE '%意见%' OR `article_title` LIKE '%规划%'
                ORDER BY `publish_time` DESC LIMIT 3
            """
            policies = db.query_business_db(policies_sql)
            db.log_event(user_id, "industry", "INFO", f"全行业查询通用政策成功，获得 {len(policies)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"全行业通用政策查询异常: {e}")

        try:
            weiban_sql = """
                SELECT `article_title` AS `标题`, `article_content` AS `正文`, `article_url` AS `网址`, `wechat_name` AS `发布单位`, `publish_time` AS `发布时间`
                FROM weixin_deepseek_extract_d
                WHERE (`article_title` LIKE '%政策%' OR `article_title` LIKE '%指南%' OR `article_title` LIKE '%办法%')
                  AND (`wechat_name` LIKE '%发布%' OR `wechat_name` LIKE '%上海%' OR `wechat_name` LIKE '%临港%')
                ORDER BY `publish_time` DESC LIMIT 3
            """
            weiban_policies = db.query_business_db(weiban_sql)
            db.log_event(user_id, "industry", "INFO", f"全行业查询地方委办局政策成功，获得 {len(weiban_policies)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"全行业地方委办局政策查询异常: {e}")
            
        try:
            news_sql = """
                SELECT `article_title` AS `标题`, `article_content` AS `内容`, `wechat_name` AS `来源`, `publish_time` AS `发布日期`, `article_url` AS `URL` 
                FROM weixin_deepseek_extract_d 
                WHERE `NewsTag` IN ('签约', '市级领导人调研', '区级领导人调研', '开会')
                ORDER BY `publish_time` DESC LIMIT 3
            """
            news = db.query_business_db(news_sql)
            db.log_event(user_id, "industry", "INFO", f"全行业查询新闻成功，获得 {len(news)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"全行业新闻查询异常: {e}")
    else:
        keyword_clean = matched_key.replace("行业", "")
        params = {"kw": f"%{keyword_clean}%"}
        
        try:
            # A. 检索微信去重公众号文章库 (weixin_deepseek_extract_d) - 画像核心文本源
            articles_sql = """
                SELECT `article_title` AS `title`, `article_content` AS `content`, `article_url` AS `link`, `publish_time` AS `date`, `wechat_name` AS `name`
                FROM weixin_deepseek_extract_d 
                WHERE (`article_title` LIKE :kw OR `article_content` LIKE :kw OR `Industry1` LIKE :kw OR `Industry2` LIKE :kw OR `Industry3` LIKE :kw)
                ORDER BY `publish_time` DESC LIMIT 5
            """
            articles = db.query_business_db(articles_sql, params)
            db.log_event(user_id, "industry", "INFO", f"行业 '{matched_key}' 查询微信动态表成功，获得 {len(articles)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"行业微信文章查询异常: {e}")

        try:
            policies_sql = """
                SELECT `article_title` AS `标题`, `article_content` AS `正文`, `article_url` AS `网址`, `wechat_name` AS `发布单位`, `publish_time` AS `发布时间` 
                FROM weixin_deepseek_extract_d 
                WHERE (`article_title` LIKE :kw OR `article_content` LIKE :kw OR `Industry1` LIKE :kw OR `Industry2` LIKE :kw OR `Industry3` LIKE :kw)
                  AND (`article_title` LIKE '%政策%' OR `article_title` LIKE '%通知%' OR `article_title` LIKE '%意见%' OR `article_title` LIKE '%规划%')
                ORDER BY `publish_time` DESC LIMIT 3
            """
            policies = db.query_business_db(policies_sql, params)
            db.log_event(user_id, "industry", "INFO", f"行业 '{matched_key}' 查询通用政策成功，获得 {len(policies)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"行业通用政策查询异常: {e}")

        try:
            weiban_sql = """
                SELECT `article_title` AS `标题`, `article_content` AS `正文`, `article_url` AS `网址`, `wechat_name` AS `发布单位`, `publish_time` AS `发布时间`
                FROM weixin_deepseek_extract_d
                WHERE (`article_title` LIKE :kw OR `article_content` LIKE :kw OR `Industry1` LIKE :kw OR `Industry2` LIKE :kw OR `Industry3` LIKE :kw)
                  AND (`article_title` LIKE '%政策%' OR `article_title` LIKE '%指南%' OR `article_title` LIKE '%办法%')
                  AND (`wechat_name` LIKE '%发布%' OR `wechat_name` LIKE '%上海%' OR `wechat_name` LIKE '%临港%')
                ORDER BY `publish_time` DESC LIMIT 3
            """
            weiban_policies = db.query_business_db(weiban_sql, params)
            db.log_event(user_id, "industry", "INFO", f"行业 '{matched_key}' 查询地方委办局政策成功，获得 {len(weiban_policies)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"行业地方委办局政策查询异常: {e}")
            
        try:
            news_sql = """
                SELECT `article_title` AS `标题`, `article_content` AS `内容`, `wechat_name` AS `来源`, `publish_time` AS `发布日期`, `article_url` AS `URL` 
                FROM weixin_deepseek_extract_d 
                WHERE (`article_title` LIKE :kw OR `article_content` LIKE :kw OR `Industry1` LIKE :kw OR `Industry2` LIKE :kw OR `Industry3` LIKE :kw)
                  AND (`NewsTag` IN ('签约', '市级领导人调研', '区级领导人调研', '开会') OR `article_title` LIKE '%签约%' OR `article_title` LIKE '%合作%' OR `article_title` LIKE '%项目%')
                ORDER BY `publish_time` DESC LIMIT 3
            """
            news = db.query_business_db(news_sql, params)
            db.log_event(user_id, "industry", "INFO", f"行业 '{matched_key}' 查询新闻成功，获得 {len(news)} 条记录。")
        except Exception as e:
            db.log_event(user_id, "industry", "ERROR", f"行业新闻查询异常: {e}")
        
    # 2. 构造 AI 扩写上下文
    articles_context_list = []
    for idx, a in enumerate(articles):
        a_title = a.get("title") or "无标题"
        a_date = a.get("date") or "未知时间"
        a_body = (a.get("content") or "")[:350]
        articles_context_list.append(
            f"微信舆情文章 {idx+1}: {a_title}\n  发布时间: {a_date}\n  内容摘要: {a_body}"
        )
    articles_context = "\n\n".join(articles_context_list) if articles_context_list else "无相关最新行业微信舆情文章数据。"

    policies_context_list = []
    for idx, p in enumerate(policies):
        p_title = p.get("标题") or "无标题"
        p_unit = p.get("发布单位") or "未知单位"
        p_time = p.get("发布时间") or "未知时间"
        p_body = (p.get("正文") or "")[:400]
        policies_context_list.append(
            f"国家政策 {idx+1}: {p_title}\n  发布单位: {p_unit}\n  发布时间: {p_time}\n  内容摘要: {p_body}"
        )
    policies_context = "\n\n".join(policies_context_list) if policies_context_list else "无相关最新国家与行业政策数据。"

    weiban_context_list = []
    for idx, p in enumerate(weiban_policies):
        p_title = p.get("标题") or "无标题"
        p_unit = p.get("发布单位") or "未知单位"
        p_time = p.get("发布时间") or "未知时间"
        p_body = (p.get("正文") or "")[:400]
        weiban_context_list.append(
            f"地方政策 {idx+1}: {p_title}\n  发文部门: {p_unit}\n  发布时间: {p_time}\n  内容摘要: {p_body}"
        )
    weiban_context = "\n\n".join(weiban_context_list) if weiban_context_list else "无相关最新地方委办局政策数据。"
    
    news_context_list = []
    for idx, n in enumerate(news):
        n_title = n.get("标题") or "无标题"
        n_src = n.get("来源") or "未知来源"
        n_date = n.get("发布日期") or "未知日期"
        n_body = (n.get("内容") or "")[:400]
        news_context_list.append(
            f"新闻 {idx+1}: {n_title}\n  来源: {n_src}\n  发布日期: {n_date}\n  内容摘要: {n_body}"
        )
    news_context = "\n\n".join(news_context_list) if news_context_list else "无相关最新新闻动态。"
        
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    
    # HTML 文件物理保存路径
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)
    
    filename = f"industry_report_{matched_key}.html"
    dest_path = os.path.join(static_dir, filename)
    web_url = f"/static/generated/{filename}"
    
    # 3. 尝试使用 AI 深度扩写或动态生成章节内容
    if api_key and "your_api_key" not in api_key:
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            if is_all_industries:
                prompt = (
                    f"你是一个资深行业分析师。用户请求一份覆盖全行业（包含26个支柱产业）的宏观深度汇编报告。\n"
                    f"我们预置了26个行业的详细章节，现在需要你根据以下从业务数据库中检索到的最新宏观微信舆情、国家/地方政策与上海新闻动态，"
                    f"为这份报告撰写一个极具洞察力的专业大标题，以及一段结构严密的前言导读（Summary）。\n\n"
                    f"【最新检索到的宏观微信舆情 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{articles_context}\n\n"
                    f"【最新检索到的宏观国家与行业政策 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{policies_context}\n\n"
                    f"【最新检索到的地方委办局政策 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{weiban_context}\n\n"
                    f"【最新检索到的上海宏观新闻 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{news_context}\n\n"
                    f"要求：返回一个 JSON 对象，必须且只能包含以下两个字段：\n"
                    f"1. 'title': 该汇编报告的专业主标题 (例如: '2026年中国全行业前沿趋势与商业洞察汇编报告'，要求有深度、有见解)\n"
                    f"2. 'summary': 该报告的前言导读 (字数在 180-250 字左右，融合同步的宏观数据与政策热点)\n\n"
                    f"格式示例：\n"
                    f"{{\n"
                    f"  \"title\": \"2026年中国全行业前沿趋势与商业洞察汇编报告\",\n"
                    f"  \"summary\": \"前言导读内容...\"\n"
                    f"}}\n"
                    f"注意：只返回标准的 JSON 数据，不要包含 ```json markdown 块包裹，也不要有任何其他解释性话语。"
                )
            elif is_dynamic:
                keyword_clean = matched_key.replace("行业", "")
                prompt = (
                    f"你是一个资深行业分析师。用户请求一份关于《{matched_key}》的深度分析报告。\n"
                    f"请为你设计并撰写一份结构完整、逻辑严密、措辞专业且高度相关的行业报告。每个章节字数在 350-400 字左右，正文支持标准的 Markdown 列表与加粗排版。\n"
                    f"我们在业务数据库中检索到了以下相关的最新行业微信舆情、最新行业政策与上海新闻动态，请灵活自然地融合这些数据与事实：\n\n"
                    f"【最新检索到的行业微信舆情 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{articles_context}\n\n"
                    f"【最新检索到的国家与行业政策 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{policies_context}\n\n"
                    f"【最新检索到的地方委办局政策 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{weiban_context}\n\n"
                    f"【最新检索到的上海新闻 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{news_context}\n\n"
                    f"要求：返回一个 JSON 对象，必须且只能包含以下三个字段：\n"
                    f"1. 'title': 该报告的专业主标题 (例如: '2026年中国{keyword_clean}行业前沿趋势与商业洞察报告')\n"
                    f"2. 'summary': 该报告的前言导读 (字数在 150-200 字左右)\n"
                    f"3. 'chapters': 报告 of 章节列表 (必须刚好是 5个章节，每个章节包含 'title' 章节标题 和 'content' 章节正文，内容融合上面的数据库情报，不能包含占位符。)\n\n"
                    f"5个章节的标题和主题必须严格定义为：\n"
                    f"  - 章节一：'一、 什么是{keyword_clean}（产业简介）' (对产业进行宏观介绍，阐述产业定义与背景)\n"
                    f"  - 章节二：'二、 {keyword_clean}近期政策' (必须融合检索到的国家及地方/上海政策规划，阐述政策红利)\n"
                    f"  - 章节三：'三、 {keyword_clean}的市场空间（运营商合作机会）' (阐述产业市场空间以及运营商可以参与的方向，例如智算中心、云网融合、安全专网等)\n"
                    f"  - 章节四：'四、 三大运营商成功实践案例' (必须具体阐述中国电信、中国移动、中国联通三大运营商在该行业的签约、合作与具体落地项目实践)\n"
                    f"  - 章节五：'五、 {keyword_clean}上海代表企业介绍' (必须整理上海本土的代表性企业、核心业务及方向)\n\n"
                    f"格式示例：\n"
                    f"{{\n"
                    f"  \"title\": \"2026年中国{keyword_clean}行业前沿趋势与商业洞察报告\",\n"
                    f"  \"summary\": \"前言导读内容...\",\n"
                    f"  \"chapters\": [\n"
                    f"    {{\"title\": \"一、 什么是{keyword_clean}（产业简介）\", \"content\": \"正文段落一...\"}},\n"
                    f"    {{\"title\": \"二、 {keyword_clean}近期政策\", \"content\": \"正文段落二...\"}},\n"
                    f"    {{\"title\": \"三、 {keyword_clean}的市场空间（运营商合作机会）\", \"content\": \"正文段落三...\"}},\n"
                    f"    {{\"title\": \"四、 三大运营商成功实践案例\", \"content\": \"正文段落四...\"}},\n"
                    f"    {{\"title\": \"五、 {keyword_clean}上海代表企业介绍\", \"content\": \"正文段落五...\"}}\n"
                    f"  ]\n"
                    f"}}\n"
                    f"注意：只返回标准的 JSON 数据，不要包含 ```json markdown 块包裹，也不要有任何其他解释性话语。"
                )
            else:
                prompt = (
                    f"你是一个资深行业分析师。请针对行业报告《{title}》，根据以下大纲要点以及我们从业务数据库中检索到的最新行业微信舆情、最新行业政策与上海新闻动态，"
                    f"进行内容深度充实与专业润色，每个章节字数扩写至 350-400 字左右，正文支持标准的 Markdown 列表与加粗排版。\n"
                    f"在扩写过程中，请务必灵活并自然地融合最新公众号舆情、最新政策和新闻动态中的真实数据、发布单位和事实（如引述相关政策、新闻或公众号文章），以极大增强报告的时效性与权威性。\n\n"
                    f"【原报告基本结构】:\n"
                    f"导读摘要: {summary}\n"
                    f"章节大纲: {json.dumps(chapters, ensure_ascii=False)}\n\n"
                    f"【最新检索到的行业微信舆情 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{articles_context}\n\n"
                    f"【最新检索到的国家与行业政策 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{policies_context}\n\n"
                    f"【最新检索到的地方委办局政策 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{weiban_context}\n\n"
                    f"【最新检索到的上海新闻 (来自 weixin_deepseek_extract_d)】:\n"
                    f"{news_context}\n\n"
                    f"要求：返回一个 JSON 对象，包含键 'summary' (对前言导读进行扩充和优化，字数在 150-200 字左右) 和 'chapters' (格式与原大纲一致，必须包含刚好 5 个章节，仅包含 'title' 和 'content' 字段)。例如：\n"
                    f"{{\n"
                    f"  \"summary\": \"结合最新政策与动态扩充后的前言导读...\",\n"
                    f"  \"chapters\": [\n"
                    f"    {{\"title\": \"一、 什么是...\", \"content\": \"融合了最新政策与新闻事实的扩写段落一...\"}},\n"
                    f"    {{\"title\": \"二、 ...\", \"content\": \"扩写段落二...\"}},\n"
                    f"    {{\"title\": \"三、 ...\", \"content\": \"扩写段落三...\"}},\n"
                    f"    {{\"title\": \"四、 ...\", \"content\": \"扩写段落四...\"}},\n"
                    f"    {{\"title\": \"五、 ...\", \"content\": \"扩写段落五...\"}}\n"
                    f"  ]\n"
                    f"}}\n"
                    f"注意：只返回标准的 JSON 数据，不要包含 ```json markdown 块包裹，也不要有任何其他解释性话语。"
                )
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "你是一个严谨的行业报告大牛，只会输出干净合法的 JSON 对象，根节点必须是花括号 {}。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                timeout=60.0
            )
            
            content = response.choices[0].message.content
            content_clean = content.strip()
            if content_clean.startswith("```"):
                if content_clean.startswith("```json"):
                    content_clean = content_clean[7:]
                else:
                    content_clean = content_clean[3:]
                if content_clean.endswith("```"):
                    content_clean = content_clean[:-3]
                content_clean = content_clean.strip()
            
            try:
                parsed_data = json.loads(content_clean)
            except Exception:
                import re
                content_clean = re.sub(r'[\x00-\x1F\x7F]', '', content_clean)
                parsed_data = json.loads(content_clean)
            if isinstance(parsed_data, dict):
                if "title" in parsed_data and (is_dynamic or is_all_industries):
                    title = parsed_data["title"]
                if "chapters" in parsed_data and not is_all_industries:
                    chapters = parsed_data["chapters"]
                if "summary" in parsed_data:
                    summary = parsed_data["summary"]
            db.log_event(user_id, "industry", "INFO", f"成功调用 DeepSeek 大模型完成了行业报告的智能生成/扩写。")
        except Exception as e:
            db.log_event(user_id, "industry", "WARNING", f"DeepSeek 行业报告 AI 生成/扩写服务异常: {e}，降级使用备用大纲。")
            if is_all_industries:
                # Keep predefined 26 industries title/summary/chapters
                pass
            elif is_dynamic:
                # 动态生成失败，回退为使用内置通信行业数据作为最终大纲
                backup_data = INDUSTRIES["通信行业"]
                title = backup_data["title"]
                summary = backup_data["summary"]
                chapters = backup_data["chapters"]

    # 4. 渲染生成 HTML
    generate_html_report(dest_path, title, summary, chapters, policies=policies, weiban_policies=weiban_policies, news=news)
    db.log_event(user_id, "industry", "INFO", f"HTML 报告文档编译成功，已写入本地: {dest_path}")
    
    # 5. 触发 Webhook 机器人推送
    webhook_url = os.getenv("ROBOT_WEBHOOK_URL", "")
    full_download_url = f"http://127.0.0.1:8000{web_url}"
    
    push_text = (
        f"**报告名称**：《{title}》\n"
        f"**覆盖行业**：{matched_key}\n"
        f"**核心摘要**：{summary[:90]}..."
    )
    
    webhook_status = send_to_webhook(webhook_url, push_text, full_download_url)
    db.log_event(user_id, "industry", "INFO", f"企业聊天机器人 Webhook 推送执行完毕，状态: {webhook_status['status']}", json.dumps(webhook_status, ensure_ascii=False))
    
    return {
        "type": "file_link",
        "file_type": "html",
        "title": title,
        "url": web_url,
        "full_url": full_download_url,
        "webhook_pushed": webhook_status["status"] == "success" or "mock" in webhook_status["status"]
    }
