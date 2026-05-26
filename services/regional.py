# -*- coding: utf-8 -*-
"""
regional.py - 场景2：区级报告。生成集成 ECharts 的精美交互式 HTML 报告。
"""

import os
import json
from utils.mock_db import REGIONS
from utils.file_helper import ensure_dir
import utils.db_helper as db

def handle(keyword: str, user_id: int = None) -> dict:
    """
    根据关键字识别区域，拉取数据生成经济分析 HTML 报告，返回报告的访问 URL。
    """
    if not keyword:
        keyword = "静安区"
        
    # 匹配区域数据 (用作兜底)
    region_data = None
    matched_key = None
    for k, v in REGIONS.items():
        if keyword in k or k in keyword:
            region_data = v
            matched_key = k
            break
            
    if not region_data:
        region_data = REGIONS["静安区"]
        matched_key = "静安区"
        
    db.log_event(user_id, "regional", "INFO", f"开始为区域 '{matched_key}' 生成 ECharts 交互式网页报告。")
    
    # 提取区域关键字
    region_keyword = matched_key.replace("区", "")
    params = {"region": f"%{region_keyword}%"}
    
    db_ok = False
    gdp_val = 0
    gdp_growth_val = 0.0
    pie_data = []
    bar_categories = []
    potential_scores = []
    description_text = region_data['description']
    
    # 默认模板渲染变量
    report_title = f"2026年{matched_key}经济运行洞察报告"
    metric_1_label = "全区生产总值 (GDP)"
    metric_1_val = f"{region_data['gdp_2025']} 亿元"
    metric_2_label = "GDP 同比增速"
    metric_2_val = f"+{region_data['gdp_growth']}%"
    metric_1_color_class = "blue-text"
    metric_2_color_class = "green-text"
    
    chart_1_title = "核心支柱产业增加值占比"
    chart_2_title = "重点发展行业成长红利指数"
    chart_1_formatter = "{b}: {c}%"
    chart_2_formatter = "{c} 分"
    
    try:
        # 1. 统计企业总数与累计补贴金额
        summary_sql = "SELECT SUM(`补贴金额万元`) AS total_subsidy, COUNT(DISTINCT `企业名称`) AS ent_count FROM ranking_ent_dtl_clue WHERE `客户区局` LIKE :region"
        summary_res = db.query_business_db(summary_sql, params)
        
        # 2. 统计工商行业分布（饼图）
        industry_sql = "SELECT `工商行业` AS industry, COUNT(*) AS cnt FROM ranking_ent_dtl_clue WHERE `客户区局` LIKE :region GROUP BY `工商行业` ORDER BY cnt DESC LIMIT 5"
        industry_res = db.query_business_db(industry_sql, params)
        
        # 3. 统计补贴金额 Top 5 的企业（条形图）
        top_ent_sql = "SELECT `企业名称` AS company, `补贴金额万元` AS subsidy FROM ranking_ent_dtl_clue WHERE `客户区局` LIKE :region AND `补贴金额万元` IS NOT NULL ORDER BY `补贴金额万元` DESC LIMIT 5"
        top_ent_res = db.query_business_db(top_ent_sql, params)
        
        # 4. 统计该行政区域内落地的大型招商项目数量 (zq_dtl_shnews_yyy)
        news_sql = "SELECT COUNT(*) AS news_count FROM zq_dtl_shnews_yyy WHERE `项目落地地区` LIKE :region OR `内容` LIKE :region"
        news_res = db.query_business_db(news_sql, params)
        project_count = news_res[0].get("news_count", 0) if news_res else 0
        
        # 5. 统计该行政区相关的政策总数 (地方委办局政策 + 通用政策)
        weiban_sql = "SELECT COUNT(*) AS policy_count FROM burneau_weiban_policy_dtl WHERE `委办局` LIKE :region OR `政策名称` LIKE :region"
        weiban_res = db.query_business_db(weiban_sql, params)
        weiban_count = weiban_res[0].get("policy_count", 0) if weiban_res else 0
        
        onenet_sql = "SELECT COUNT(*) AS policy_count FROM zq_dtl_onenet_all WHERE `正文` LIKE :region OR `标题` LIKE :region"
        onenet_res = db.query_business_db(onenet_sql, params)
        onenet_count = onenet_res[0].get("policy_count", 0) if onenet_res else 0
        
        total_policies = weiban_count + onenet_count
        
        if summary_res and summary_res[0].get("ent_count", 0) > 0:
            gdp_val = int(summary_res[0].get("ent_count") or 0)
            gdp_growth_val = round(float(summary_res[0].get("total_subsidy") or 0.0), 2)
            
            # 填充饼图
            for row in industry_res:
                ind = row.get("industry") or "其他"
                if ind.strip():
                    pie_data.append({
                        "name": ind,
                        "value": int(row.get("cnt") or 0)
                    })
                    
            # 填充条形图 (倒序排列，因为 ECharts 柱状图自下而上画)
            for row in reversed(top_ent_res):
                company = row.get("company") or "未知企业"
                subsidy = round(float(row.get("subsidy") or 0.0), 2)
                bar_categories.append(company)
                potential_scores.append(subsidy)
                
            # 覆盖模板渲染变量
            report_title = f"2026年{matched_key}重点企业扶持与政策数据洞察报告"
            metric_1_label = "全区企业总数 (去重)"
            metric_1_val = f"{gdp_val} 家"
            metric_2_label = "累计补贴扶持金额"
            metric_2_val = f"{gdp_growth_val} 万元"
            
            chart_1_title = "支柱产业企业数量分布 Top 5"
            chart_2_title = "扶持资金 Top 5 标杆企业名录"
            chart_1_formatter = "{b}: {c}家"
            chart_2_formatter = "{c} 万元"
            
            top_3_companies = [r.get('company') for r in top_ent_res[:3]]
            description_text = (
                f"根据本系统实时监测 of MySQL 业务数据分析，当前在 {matched_key} 分配的重点企业去重总计达 **{gdp_val}** 家，"
                f"全区企业累计已获得各委办局财政扶持与补贴资金总计达 **{gdp_growth_val}** 万元。在产业结构方面，全区以 "
                f"'{pie_data[0]['name'] if pie_data else '支柱产业'}' 和 '{pie_data[1]['name'] if len(pie_data) > 1 else '高新技术'}' 为主要企业集群。"
                f"在招商落地与政策红利方面，近期累计在 {matched_key} 落地重大招商签约项目 **{project_count}** 个，"
                f"发布地方与行业扶持政策达 **{total_policies}** 项（包含委办局政策 **{weiban_count}** 项）。"
                f"其中，补贴资金排名前列的标杆企业包括 {', '.join(top_3_companies)} 等。建议客户经理以此作为突破口进行业务深耕。"
            )
            db_ok = True
    except Exception as db_err:
        db.log_event(user_id, "regional", "ERROR", f"从业务库读取区域数据失败: {db_err}")
        db_ok = False
        
    if not db_ok:
        # 回退至 mock 数据
        pie_data = []
        for industry_name, share_val in region_data['industry_gdp_share'].items():
            pie_data.append({
                "name": industry_name,
                "value": share_val
            })
        bar_categories = region_data['key_industries']
        potential_scores = [93, 86, 82, 75, 68][:len(bar_categories)]
        description_text = region_data['description']
        
    # 确定保存路径（在 static/generated/ 下）
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "static", "generated")
    ensure_dir(static_dir)
    
    html_filename = f"regional_{matched_key}.html"
    html_filepath = os.path.join(static_dir, html_filename)
    html_web_url = f"/static/generated/{html_filename}"
    
    # 构造 HTML
    html_content = f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>{report_title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Noto+Sans+SC:wght@300;400;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --text-color: #f8fafc;
            --glass-bg: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.08);
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --card-bg: rgba(17, 24, 39, 0.7);
        }}
        body {{
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(37, 99, 235, 0.1) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.1) 0px, transparent 50%);
            color: var(--text-color);
            font-family: 'Outfit', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
            min-height: 100vh;
            box-sizing: border-box;
        }}
        .container {{
            max-width: 900px;
            width: 100%;
            background: rgba(15, 23, 42, 0.6);
            backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
            box-sizing: border-box;
        }}
        header {{
            text-align: center;
            border-bottom: 1px solid var(--glass-border);
            padding-bottom: 24px;
            margin-bottom: 30px;
        }}
        h1 {{
            font-size: 28px;
            font-weight: 700;
            margin: 0 0 10px 0;
            background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            font-size: 14px;
            color: #64748b;
            margin: 0;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
            transition: transform 0.3s ease;
        }}
        .card:hover {{
            transform: translateY(-2px);
        }}
        .card-label {{
            font-size: 12px;
            color: #94a3b8;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }}
        .card-value {{
            font-size: 28px;
            font-weight: 700;
        }}
        .blue-text {{ color: var(--accent-blue); }}
        .green-text {{ color: var(--accent-green); }}
        
        .charts-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        @media (max-width: 768px) {{
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
            .metrics {{
                grid-template-columns: 1fr;
            }}
        }}
        .chart-card {{
            background: var(--card-bg);
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
        }}
        .chart-title {{
            font-size: 15px;
            font-weight: 600;
            color: #cbd5e1;
            margin-top: 0;
            margin-bottom: 20px;
            border-left: 3px solid var(--accent-blue);
            padding-left: 10px;
        }}
        .insight-section {{
            background: rgba(59, 130, 246, 0.05);
            border: 1px solid rgba(59, 130, 246, 0.15);
            border-radius: 16px;
            padding: 24px;
        }}
        .insight-title {{
            font-size: 16px;
            font-weight: 700;
            color: var(--accent-blue);
            margin-top: 0;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .insight-content {{
            font-size: 14px;
            line-height: 1.8;
            color: #cbd5e1;
            margin: 0;
            text-align: justify;
        }}
        
        /* Floating print button styling */
        .actions-bar {{
            display: flex;
            justify-content: flex-end;
            margin-bottom: 20px;
        }}
        .btn {{
            background: rgba(255, 255, 255, 0.05);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.15);
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
            backdrop-filter: blur(10px);
        }}
        .btn:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: white;
            border-color: rgba(255, 255, 255, 0.25);
        }}
        
        @media print {{
            body {{
                background: white;
                color: black;
                padding: 0;
            }}
            .container {{
                background: white;
                border: none;
                box-shadow: none;
                padding: 0;
                max-width: 100%;
            }}
            h1 {{
                color: black;
                -webkit-text-fill-color: initial;
            }}
            .no-print {{
                display: none !important;
            }}
            .chart-card {{
                background: white;
                border: 1px solid #e2e8f0;
                box-shadow: none;
                color: black;
            }}
            .chart-title {{
                color: black;
                border-left-color: #2563eb;
            }}
            .insight-section {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                color: black;
            }}
            .insight-title {{
                color: #2563eb;
            }}
            .insight-content {{
                color: #334155;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="actions-bar no-print">
            <button class="btn" onclick="window.print()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
                打印或保存
            </button>
        </div>
        <header>
            <h1>{report_title}</h1>
            <p class="subtitle">AI 智能分析引擎 & ECharts 交互式可视化看板</p>
        </header>
        <div class="metrics">
            <div class="card">
                <div class="card-label">{metric_1_label}</div>
                <div class="card-value {metric_1_color_class}">{metric_1_val}</div>
            </div>
            <div class="card">
                <div class="card-label">{metric_2_label}</div>
                <div class="card-value {metric_2_color_class}">{metric_2_val}</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-card">
                <h3 class="chart-title">{chart_1_title}</h3>
                <div id="pie-chart" style="width: 100%; height: 320px;"></div>
            </div>
            <div class="chart-card">
                <h3 class="chart-title">{chart_2_title}</h3>
                <div id="bar-chart" style="width: 100%; height: 320px;"></div>
            </div>
        </div>
        
        <div class="insight-section">
            <h3 class="insight-title">💡 区域发展定位与商业合作机会建议</h3>
            <p class="insight-content">{description_text}</p>
        </div>
    </div>

    <script>
        // 初始化 ECharts 数据
        const pieData = {json.dumps(pie_data, ensure_ascii=False)};
        const barCategories = {json.dumps(bar_categories, ensure_ascii=False)};
        const barValues = {json.dumps(potential_scores, ensure_ascii=False)};

        // 1. 饼图
        const pieChart = echarts.init(document.getElementById('pie-chart'), null, {{ devicePixelRatio: 2 }});
        const pieOption = {{
            backgroundColor: 'transparent',
            tooltip: {{
                trigger: 'item',
                formatter: '{chart_1_formatter}'
            }},
            legend: {{
                bottom: '0%',
                left: 'center',
                textStyle: {{ color: '#94a3b8', fontSize: 11 }},
                itemWidth: 10,
                itemHeight: 10
            }},
            series: [
                {{
                    name: '分布数量',
                    type: 'pie',
                    radius: ['40%', '65%'],
                    center: ['50%', '42%'],
                    avoidLabelOverlap: false,
                    itemStyle: {{
                        borderRadius: 6,
                        borderColor: '#0b0f19',
                        borderWidth: 2
                    }},
                    label: {{
                        show: false
                    }},
                    emphasis: {{
                        label: {{
                            show: true,
                            fontSize: '12',
                            fontWeight: 'bold',
                            color: '#f8fafc',
                            formatter: '{chart_1_formatter}'
                        }}
                    }},
                    labelLine: {{
                        show: false
                    }},
                    data: pieData
                }}
            ],
            color: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899']
        }};
        pieChart.setOption(pieOption);

        // 2. 柱状图
        const barChart = echarts.init(document.getElementById('bar-chart'), null, {{ devicePixelRatio: 2 }});
        const barOption = {{
            backgroundColor: 'transparent',
            tooltip: {{
                trigger: 'axis',
                axisPointer: {{ type: 'shadow' }}
            }},
            grid: {{
                left: '4%',
                right: '12%',
                bottom: '3%',
                top: '5%',
                containLabel: true
            }},
            xAxis: {{
                type: 'value',
                splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.06)', type: 'dashed' }} }},
                axisLabel: {{ color: '#94a3b8', fontSize: 10 }},
                axisLine: {{ show: false }}
            }},
            yAxis: {{
                type: 'category',
                data: barCategories,
                axisLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.1)' }} }},
                axisLabel: {{ color: '#cbd5e1', fontSize: 11 }}
            }},
            series: [
                {{
                    name: '补贴金额',
                    type: 'bar',
                    data: barValues,
                    barWidth: '35%',
                    itemStyle: {{
                        borderRadius: [0, 4, 4, 0],
                        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                            {{ offset: 0, color: '#3b82f6' }},
                            {{ offset: 1, color: '#8b5cf6' }}
                        ])
                    }},
                    label: {{
                        show: true,
                        position: 'right',
                        formatter: '{chart_2_formatter}',
                        color: '#94a3b8',
                        fontWeight: 'bold',
                        fontSize: 10
                    }}
                }}
            ]
        }};
        barChart.setOption(barOption);

        // 响应式
        window.addEventListener('resize', () => {{
            pieChart.resize();
            barChart.resize();
        }});
    </script>
</body>
</html>
"""
    with open(html_filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    db.log_event(user_id, "regional", "INFO", f"区域分析报告网页生成完毕。保存路径: {html_filepath}")
    
    return {
        "type": "html_link",
        "url": html_web_url,
        "region_name": matched_key,
        "gdp": metric_1_val,
        "gdp_growth": metric_2_val
    }
