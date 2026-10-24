from __future__ import annotations

import unittest
from unittest.mock import patch

from app import services


class TopicMiningDirectionTests(unittest.TestCase):
    def test_real_estate_listing_is_rejected_for_technology_channel(self) -> None:
        references = [
            {
                "title": "熙悦京景售楼处 官方首页 楼盘详情 最新价格 户型图 容积率",
                "snippet": "欢迎预约看房，查看在售房源和楼盘地址。",
                "url": "https://example.com/property/123",
            }
        ]
        filtered = services.filter_current_news_references_for_channel(
            references,
            ["AI工具", "智能设备", "消费电子", "科技新闻"],
        )
        self.assertEqual(filtered, [])

    def test_real_estate_listing_is_allowed_for_property_channel(self) -> None:
        reference = {
            "title": "熙悦京景楼盘最新价格与户型图",
            "snippet": "在售房源、容积率和交房时间更新。",
            "url": "https://example.com/property/123",
        }
        self.assertEqual(
            services._topic_reference_block_reason(reference, ["房地产", "北京楼盘"]),
            "",
        )

    def test_candidate_scoring_drops_unrelated_property_marketing_topic(self) -> None:
        candidates = [
            {
                "title": "熙悦京景楼盘最新价格",
                "brief": "售楼处公布户型图、容积率和预约看房方式。",
                "score": 4.8,
            }
        ]
        scored = services.apply_current_news_candidate_scores(
            candidates,
            [],
            ["科技情报站", "AI工具", "智能设备"],
        )
        self.assertEqual(scored, [])

    def test_stitched_seo_download_page_is_rejected(self) -> None:
        reference = {
            "title": "kb.开宝体育发布全新赛事预测平台，推动体育竞猜行业数字化转型",
            "snippet": (
                "妇联直播间分享，威尼斯人成官网吗入口发布AI营销引擎V3.0，"
                "桥球Product Hunt口榜冠军，爱游戏体育手游下载；"
                "极致体验与隐私保护，功能、安全与用户体验全面解析，"
                "南宫娱乐2.8官网最新版全面解析与功能指南，滚球体育网站安卓版下载安装最新版。"
            ),
            "url": "https://example.com/kb-seo-page",
        }
        reason = services._topic_reference_block_reason(
            reference,
            ["科技情报站", "AI工具", "智能设备", "消费电子"],
        )
        self.assertIn("SEO", reason)
        self.assertEqual(
            services.filter_current_news_references_for_channel(
                [reference],
                ["科技情报站", "AI工具", "智能设备", "消费电子"],
            ),
            [],
        )

    def test_navigation_and_gambling_farm_page_is_rejected(self) -> None:
        reference = {
            "title": "斗体育vip网页版登录借AI预测崛起，冲击体育数据服务产业新格局",
            "snippet": (
                "首页 要闻 妇联直播间 聚焦 巾帼风采 家教家议 法律帮助 健康生活 "
                "婚姻与家庭 图秀 视频 数据平台 微博 Qzone 微信 微信扫一扫 文章正文 "
                "从体育科技展看斗体育vip网页版登录 FA9955.CC 的AI算力需求。"
            ),
            "url": "https://fa9955.cc/article/123",
        }
        reason = services._topic_reference_block_reason(
            reference,
            ["科技情报站", "AI工具", "智能设备"],
        )
        self.assertIn("SEO", reason)
        self.assertEqual(
            services.filter_current_news_references_for_channel(
                [reference],
                ["科技情报站", "AI工具", "智能设备"],
            ),
            [],
        )

    def test_technical_wrapper_for_entertainment_platform_is_rejected(self) -> None:
        reference = {
            "title": "为流式渲染与AI原生交互而生 开云在线登录3.0正式发布",
            "snippet": (
                "## 行动号召 立即登录GitHub搜索KaiYunLogin，下载最新源码或体验Demo，"
                "访问官网并加入我们的社区。尊龙将打造亚洲顶级互动娱乐平台。"
            ),
            "url": "https://example.com/ai-native-login",
        }
        self.assertTrue(services._looks_like_seo_content_farm(
            f"{reference['title']} {reference['snippet']} {reference['url']}"
        ))
        self.assertEqual(
            services.filter_current_news_references_for_channel(
                [reference],
                ["科技情报站", "AI工具", "智能设备"],
            ),
            [],
        )

    def test_explicit_topic_direction_is_a_hard_reference_boundary(self) -> None:
        search_results = [
            {
                "title": "AI办公助手发布新版本",
                "snippet": "面向企业用户更新智能文档功能。",
                "url": "https://source-a.test/ai-office",
            },
            {
                "title": "汽车辅助驾驶系统发布更新",
                "snippet": "新版本改善城市道路驾驶体验。",
                "url": "https://source-b.test/car-update",
            },
        ]
        with patch.object(services, "search_deepseek_web", return_value=search_results), patch.object(
            services, "search_current_news_auxiliary", return_value=[]
        ):
            references, _ = services._mine_topic_reference_pool(
                {
                    "name": "科技情报站",
                    "topic_mining_hint": "AI工具、智能设备、汽车科技",
                    "prompt": "关注普通人能用上的科技产品。",
                },
                "汽车",
                "general",
                "2026年8月9日",
            )
        self.assertEqual([item["url"] for item in references], ["https://source-b.test/car-update"])

    def test_broad_technology_request_keeps_different_technology_tracks(self) -> None:
        search_results = [
            {
                "title": "量子计算实验取得新进展",
                "snippet": "研究团队公布新的量子计算实验结果。",
                "url": "https://source-a.test/quantum",
            },
            {
                "title": "智能汽车系统更新",
                "snippet": "车载系统更新了新的辅助驾驶功能。",
                "url": "https://source-b.test/car",
            },
        ]
        with patch.object(services, "search_deepseek_web", return_value=search_results) as grok_search, patch.object(
            services, "search_current_news_auxiliary", return_value=[]
        ):
            references, _ = services._mine_topic_reference_pool(
                {
                    "key": "科技情报站",
                    "name": "科技情报站",
                    "topic_mining_hint": "AI工具、智能设备、汽车科技",
                },
                "科技",
                "news",
                "2026年8月9日",
            )
        self.assertEqual(
            {item["url"] for item in references},
            {"https://source-a.test/quantum", "https://source-b.test/car"},
        )
        grok_search.assert_called_once()

    def test_recovers_complete_candidates_from_truncated_json(self) -> None:
        raw = '{"candidates":[{"title":"A","score":4.2},{"title":"B","score":4.1},{"title":"unfinished"'
        recovered = services._recover_truncated_json_list(raw, "candidates")
        self.assertEqual([item["title"] for item in recovered], ["A", "B"])

    def test_broad_direction_expands_to_requested_candidate_count(self) -> None:
        items = services._expand_topic_direction_candidates(
            direction="汽车",
            brand="科技情报站",
            references=[],
            existing_topics=[],
            desired_count=6,
        )
        self.assertEqual(len(items), 6)
        self.assertTrue(all(item["title"] != "汽车" for item in items))
        self.assertEqual(len({item["title"] for item in items}), 6)

    def test_specific_science_event_is_not_silently_dropped(self) -> None:
        template = {
            "key": "科技情报站",
            "name": "科技情报站",
            "brand_name": "科技情报站",
            "topic_mining_hint": "AI工具、智能设备、芯片、前沿科技",
            "prompt": "只讲有公开依据、普通人能听懂的科技事件。",
        }
        with (
            patch.object(services.storage, "projects_for_template", return_value=[]),
            patch.object(services, "_mine_topic_reference_pool", return_value=([], ["query"])),
            patch.object(services, "runtime_env", return_value={}),
            patch.object(services, "search_current_news", return_value=[]),
            patch.object(services, "search_duckduckgo", return_value=[]),
        ):
            result = services.mine_channel_topic(
                template,
                "news",
                "二维铜基高温超导体突破",
                6,
            )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["title"], "二维铜基高温超导体突破")
        self.assertEqual(result["candidates"][0]["readiness"], "review")
        self.assertEqual(result["candidates"][0]["source"], "explicit_topic")

    def test_grok2api_response_references_are_normalized(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"references":[{"title":"研究团队发布二维铜基超导结果","url":"https://example.edu/paper","snippet":"论文报告了实验结果。","published_date":"2026-08-12","source":"研究机构"}]}',
                        }
                    ],
                }
            ]
        }
        references = services._normalize_grok2api_references(payload, "二维铜基高温超导体突破", 6)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["url"], "https://example.edu/paper")
        self.assertEqual(references[0]["source"], "研究机构")

    def test_grok2api_url_citations_are_used_when_text_is_not_json(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "已完成检索。",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://journal.example.org/article",
                                    "title": "期刊论文",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        references = services._normalize_grok2api_references(payload, "超导体突破", 6)
        self.assertEqual([item["url"] for item in references], ["https://journal.example.org/article"])


if __name__ == "__main__":
    unittest.main()
