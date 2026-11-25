#!/usr/bin/env python3
"""SPEC v2.0 guardrail rules and the deterministic Pre-Gen engine (library only).

L0: five always-on baseline items. L1: twelve conditional rules in `IF trigger THEN constraints &
review focus` form, plus optional declarative custom rules from the mistake book; a rule is mounted
only when its trigger fires on the shot's structured slots or non-negated prompt semantics, and
DEPRECATED / CANDIDATE mistake-book rules are unmounted. `evaluate()` validates input schema across
three explicit modes (`nbp`, `workflow_case`, `shot`), checks cross-shot anchors (props, wardrobe,
key light, spatial side), duration vs whole-shot EN/ZH action density, and returns the verdict,
triggered rules, blocking error codes and injected constraints. `rubric_for()` builds the atomic
binary Clean-Room rubric (one observable question, one PASS and one FAIL example per item).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from shot_invariants import check_props_continuity, check_props_state, detected_headcounts, mentions_screen_or_ui

# --------------------------------------------------------------------------- rules

L0_RULES: tuple[dict[str, Any], ...] = (
    {"id": "L0-01", "title": "画质严重涂抹 / 灰模塑料感残留", "repair_route": "cross_stage_rollback_stale",
     "question": "主体区域是否出现大面积涂抹糊化、灰模/低模材质残留，或相邻镜画质骤降？",
     "pass_example": "浅景深背景虚化、胶片颗粒、高速运动的自然动态模糊、brief 指定的水墨/像素风",
     "fail_example": "灰模质感渗入成片；人脸与衣料呈蜡像塑料涂抹感；相邻镜从高清骤降为马赛克",
     "requires_audio": False, "requires_motion": False, "needs_anchor": False},
    {"id": "L0-02", "title": "人体解剖 / 手指畸变 / 误裁切", "repair_route": "slow_or_split_shot",
     "question": "可见主体是否出现多指/融手/断肢穿模、五官扭曲，或非意图的无头裁切？",
     "pass_example": "手插兜或背影遮住手臂；brief 要求的颈下特写；快速挥臂的瞬时拖影",
     "fail_example": "握杯时 6–7 指或手指融进杯壁；手臂穿透桌沿；全身镜把主角头部切掉",
     "requires_audio": False, "requires_motion": False, "needs_anchor": False},
    {"id": "L0-03", "title": "无故黑帧 / 死帧 / 切镜爆闪", "repair_route": "post_clean_plate_fix",
     "question": "片段首尾及切点前后 ±0.12s 是否有无叙事动机的黑帧、冻帧、白帧爆闪或曝光频闪？",
     "pass_example": "brief 设计的戏剧黑场；闪电/闪光灯且伴随环境光响应；刻意定格片尾卡",
     "fail_example": "切口残留 2–6 帧纯黑或冻帧；无光源变化时面部光影逐帧抽搐",
     "requires_audio": False, "requires_motion": False, "needs_anchor": False},
    {"id": "L0-04", "title": "伪文字 / 乱码水印 / 未授权字幕", "repair_route": "post_clean_plate_fix",
     "question": "画面是否出现模型自发烧录的字幕、平台水印、乱码假字或未获授权的角标文字？",
     "pass_example": "确定性后期渲染的清晰字幕或 HUD；用户批准且拼写核对过的 Logo 片尾卡",
     "fail_example": "底部自行烧出乱码字幕；海报/弹窗出现笔画融化的伪字；封面私加角标",
     "requires_audio": False, "requires_motion": False, "needs_anchor": False},
    {"id": "L0-05", "title": "时间轴物理崩坏（滑步 / 瞬移 / 主体凭空增减）", "repair_route": "slow_or_split_shot",
     "question": "连播或序列帧中是否出现脚不沾地滑步、无切镜瞬移变形，或人数/关键持物凭空增减？",
     "pass_example": "合法 editorial_cut 跳切；人物自然走出画框；遮挡物经过后的合规衔接",
     "fail_example": "走路脚底打滑漂浮；中段凭空多出陌生人的手；咖啡喝到一半凭空消失；载具单镜内变型号",
     "requires_audio": False, "requires_motion": True, "needs_anchor": False},
)

L1_RULES: dict[str, dict[str, Any]] = {
    "L1-01": {
        "title": "多人近身交互 / 对峙 / 追逐攻防", "repair_route": "cross_stage_rollback_stale",
        "constraints": ["显式声明 actor_count 与 actors，提示词人数短语不得超出 actor_count + crowd_count",
                        "每名角色绑定独立参考槽位与画框方位，不用模糊代词",
                        "攻防/追逐写清运动矢量、施力者与受力者"],
        "question": "可见人数是否符合预期，且攻防/追逐运动关系与预期动作一致？",
        "pass_example": "追击者可见逼近阻截，被追者被迫转向；有意护送时引路者在前",
        "fail_example": "承诺逃生却拍成反派在前领路开门；凭空多出第三人；双人串脸",
        "rubric_items": [
            {"id": "L1-01", "repair_route": "cross_stage_rollback_stale",
             "question": "画面可见人物数量是否守恒（未凭空多出/少人），且人物相对站位与追逐/互动方向符合预期动作？",
             "pass_example": "追击者在后逼近阻截、逃生者在前奔逃；或有意护送时引路者在前",
             "fail_example": "逃生戏拍成追击者在前替人开门；画面凭空多出未声明路人；双人五官服饰串换",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
    "L1-02": {
        "title": "手部持物特写 / 道具跨镜交接 / POV 肢体归属", "repair_route": "slow_or_split_shot",
        "constraints": ["锁定 props_state {in, out}；故意跳态须 continuity_break: true",
                        "写清接触点刚体关系，不用融进/缠绕/化开类修辞",
                        "POV 声明可见手数、袖口与腕戴物归属"],
        "question": "动作峰值帧五指与关节是否正常、持握道具形态与归属是否守恒？",
        "pass_example": "自然持握且边缘分离清晰；杯型与数量跨镜一致",
        "fail_example": "多指粘连、手穿桌沿；道具凭空消失或换款换色",
        "rubric_items": [
            {"id": "L1-02", "repair_route": "slow_or_split_shot",
             "question": "手部接触峰值帧五指与关节是否解剖正常，且所持道具外形、颜色与接触边界清晰守恒？",
             "pass_example": "五指自然握持手机侧边、接触面刚体边界清晰；杯型与持握状态一致",
             "fail_example": "手指粘连融进器物表面、手掌穿透桌面；持握道具中途变形或换色",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
    "L1-03": {
        "title": "大幅环绕 / 过肩正反打 / 侧背调度", "repair_route": "boost_identity_anchor",
        "constraints": ["挂载该角色非正面锁定视图（profile / three_quarter / back）",
                        "先锁白模站位与机位，不跨 180° 轴线（除非 allow_axis_cross 且有连续过渡）",
                        "写明固定地标左右锚定与相机起点→终点构图"],
        "question": "转侧/背影后发际线、发色与服装背面是否与多角度基准图一致，且未无动机越轴？",
        "pass_example": "转头与背影发色、领口一致；视线方向与地标左右关系守恒",
        "fail_example": "正面棕发转背影变黑发；环绕半圈后重造一张陌生人脸",
        "rubric_items": [
            {"id": "L1-03a", "repair_route": "boost_identity_anchor",
             "question": "角色转侧或背影时，发际线、发色与服装背面细节是否与基准锚点图保持同一人同一套服装？",
             "pass_example": "正面转背影发色、领口剪裁与锚点图一致，面部侧廓骨相守恒",
             "fail_example": "正面棕发转背影突变为黑发；环绕后长出另一张陌生人脸或外套换款",
             "requires_audio": False, "requires_motion": False, "needs_anchor": True},
            {"id": "L1-03b", "repair_route": "cross_stage_rollback_stale",
             "question": "镜头内人物视线朝向与背景固定地标的画面左右空间关系是否连贯、无突兀越轴跳向？",
             "pass_example": "过肩或环绕过程中人物左右关系与背景门窗方位平滑过渡、视线对位准确",
             "fail_example": "无连续运镜过渡时人物左右站位或背景门窗突然镜像翻转、视线看反方向",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
    "L1-04": {
        "title": "复杂光影 / 镜面反射 / 夜景暗部 / 液态物性", "repair_route": "boost_identity_anchor",
        "constraints": ["声明唯一主光方向、色温与补光关系，静帧底板锁暗部黑位",
                        "反射按载体运动方向写明正确轴向，禁止反向漂移",
                        "液体/污渍写物性不变量（只留在织物表面、不蔓延为伤口）"],
        "question": "首尾帧衣物底色、污渍形态与暗部黑位是否稳定，反射运动是否与载体自洽？",
        "pass_example": "暗部稳定、污渍随布料移动但性质不变；反射与位移同步",
        "fail_example": "浅灰衣料串色、墨渍蔓延至皮肤或变色、暗部噪点爆裂；倒影比人走得快",
        "rubric_items": [
            {"id": "L1-04", "repair_route": "boost_identity_anchor",
             "question": "首尾帧衣物底色、液体污渍物性与暗部主光方向是否稳定，且镜面/玻璃反射方向与主体位移自洽？",
             "pass_example": "夜景单主光稳定、墨渍仅停留在浅灰围裙表面随布料移动；玻璃反射与人物同步同向",
             "fail_example": "浅灰衣料逐渐串色、墨渍蔓延成皮肤伤口；镜中倒影与真人反向移动或脱节",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
    "L1-05": {
        "title": "屏幕 / 招牌 / HUD 界面", "repair_route": "post_clean_plate_fix",
        "constraints": ["填写 screen_ui: clean_plate_post_replace，不让模型直出可读 UI 文案",
                        "屏幕保持暗屏/纯色干净底板并预留四角，文字交确定性后期叠层",
                        "实体门头 Logo 只用用户确认过的锁定资产图"],
        "question": "屏幕与招牌区域是否为干净底板或精确锁定图形？",
        "pass_example": "暗屏反光无乱字；后期贴片透视与拼写 100% 准确",
        "fail_example": "屏幕直出乱码假字母、自造错误句子、招牌笔画融化",
        "rubric_items": [
            {"id": "L1-05", "repair_route": "post_clean_plate_fix",
             "question": "画面中的手机/电脑屏幕或招牌区域是否保持无伪字的干净底板（或与锚点图一致的清晰图形）？",
             "pass_example": "手机屏幕呈自然暗屏反光、无AI乱码文字，四角边界清晰可供后期贴片",
             "fail_example": "屏幕自发生成残缺假英文、扭曲乱码弹窗，或门头招牌笔画融化变形",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
    "L1-06": {
        "title": "高密度动作 / 短时长多节拍 / 物理因果链", "repair_route": "slow_or_split_shot",
        "constraints": ["单镜默认承载 1 主动作 + 1 反应，超出预算拆镜",
                        "关键瞬间用 OPEN ON ACTION 写进行中状态与起止身体端点",
                        "受力反馈写完整因果链：触发 → 朝向变化 → 受力方向 → 同向位移"],
        "question": "预期动作的终点是否在有效帧内真实发生，且受力方向与位移一致？",
        "pass_example": "动作在有效帧内完成，击退方向与冲量同向",
        "fail_example": "只出现蓄势或门前等待等静态起势；转身/击飞方向与受力矛盾",
        "rubric_items": [
            {"id": "L1-06", "repair_route": "slow_or_split_shot",
             "question": "预期动作的关键终点是否在画面有效帧内真实完成，且身体受力与位移方向符合物理因果？",
             "pass_example": "破门与嫌犯后退在片内完整发生，或转身奔跑远离威胁源且步态受力自洽",
             "fail_example": "全片停留在蓄势/原地等待未发生预期动作（如承诺转身逃离却原地竖拇指），或受力位移反向",
             "requires_audio": False, "requires_motion": True, "needs_anchor": False},
        ],
    },
    "L1-07": {
        "title": "对白口播 / 多人对话 / 外语发行 / 配乐同步", "repair_route": "post_clean_plate_fix",
        "constraints": ["同一时间分段至多 1 名说话者，按语速预留句尾留白（≥0.6s）",
                        "口播语种与目标发布语言一致，前置禁烧字幕约束",
                        "后期统一配乐时 native_bgm: false 且提示词只要干净人声与环境声",
                        "生造专名挂 lexicon 并扫描台词、提示词与字幕"],
        "question": "是否只有目标说话者动嘴、台词无漏读错读错语种、无残留碎 BGM？",
        "pass_example": "单人发言口型对应，专名读音正确，句尾留白完整",
        "fail_example": "双人同时动嘴；专名读成禁用变体；配乐与对白打架",
        "rubric_items": [
            {"id": "L1-07a", "repair_route": "post_clean_plate_fix",
             "question": "画面中同一发言时刻是否仅有单一目标说话者张嘴发声（同框倾听者保持闭嘴、无双人抢话）？",
             "pass_example": "发言角色口型张合自然，同框另一角色安静倾听不动嘴，句尾闭唇停顿自然",
             "fail_example": "同框两名角色同时张嘴抢话，或角色全程闭嘴却硬配画内对白",
             "requires_audio": False, "requires_motion": True, "needs_anchor": False},
            {"id": "L1-07b", "repair_route": "post_clean_plate_fix",
             "question": "音轨中说话人声的语种是否与目标语种一致（未串成其他语种或无意义乱语）？",
             "pass_example": "全段人声保持目标语种自然发音，无语种跳变",
             "fail_example": "英文台词吐出中文或夹杂无法辨识的伪外语乱音",
             "requires_audio": True, "requires_motion": True, "needs_anchor": False},
            {"id": "L1-07c", "repair_route": "post_clean_plate_fix",
             "question": "音轨台词吐字是否清晰完整、句尾收音自然而未被硬截断吞字？",
             "pass_example": "关键台词字音清晰可辨，句尾留白完整无截断",
             "fail_example": "台词含混糊音、专名严重错读，或句尾最后一个词被切镜硬生生截断",
             "requires_audio": True, "requires_motion": True, "needs_anchor": False},
            {"id": "L1-07d", "repair_route": "post_clean_plate_fix",
             "question": "音轨背景是否保持干净环境声、无未经请求的杂乱原生背景音乐（BGM）盖过人声？",
             "pass_example": "背景仅有与场景匹配的干净环境底噪，人声主次分明",
             "fail_example": "模型自发混入嘈杂碎配乐或鼓点，与对白人声互相遮盖打架",
             "requires_audio": True, "requires_motion": True, "needs_anchor": False},
        ],
    },
    "L1-08": {
        "title": "跨阶段变更（换参考图 / 改白模 / 新增道具）", "repair_route": "cross_stage_rollback_stale",
        "constraints": ["只把引用变更源头的下游白模与镜头标 STALE，未波及镜头保持有效",
                        "身份图摘要变更后旧肖像探针作废，重跑最小探针",
                        "对变更资产与 STALE 范围触发增量 Human Gate #2，签收前不批量重跑"],
        "question": "画面角色/场景外观是否与当前最新基准锚点图一致、无旧版资产特征残留？",
        "pass_example": "画面主角五官发色与新版锚点图完全一致，无旧版服饰或发色混入",
        "fail_example": "画面仍呈现已作废旧版角色发色、旧版服装或旧场景陈设",
        "rubric_items": [
            {"id": "L1-08", "repair_route": "cross_stage_rollback_stale",
             "question": "画面中角色的面部、发色、服饰及场景陈设是否与当前提供的基准锚点图一致、无异版外观混入？",
             "pass_example": "角色五官、发型与服装颜色均与当前锚点图吻合",
             "fail_example": "角色发色、脸型或主景陈设与当前锚点图明显不符",
             "requires_audio": False, "requires_motion": False, "needs_anchor": True},
        ],
    },
    "L1-09": {
        "title": "启动未点名模型 / 规格 / 未锁剧本", "repair_route": "cross_stage_rollback_stale",
        "constraints": ["STOP & WAIT：用宿主交互组件或 model_gate.py 编号菜单确认四项必选，立即结束本轮",
                        "已指定平台时画幅由平台推导；只要剧本或纯提示词时停在文本交付",
                        "付费批量前确认试价探针、余额回读与预算熔断上限"],
        "question": "画面是否为真实连续动态生成，而非用静态单图推拉缩放或黑屏凑时长冒充成片？",
        "pass_example": "人物与环境具备真实三维透视变化与自然肢体动态",
        "fail_example": "整段仅为单张静态图缓慢放大平移（Ken Burns）或大段黑屏静帧凑时长",
        "rubric_items": [
            {"id": "L1-09", "repair_route": "cross_stage_rollback_stale",
             "question": "待审视频是否呈现真实动态画面，未用单张静图生硬缩放平移或黑屏定格冒充动态成片？",
             "pass_example": "画面主体与光影具有自然帧间动态与透视变化",
             "fail_example": "整段只有一张静态图做机械放大平移，或用黑屏/冻帧硬凑时长",
             "requires_audio": False, "requires_motion": True, "needs_anchor": False},
        ],
    },
    "L1-10": {
        "title": "白模 / 灰模预演转精修视频", "repair_route": "cross_stage_rollback_stale",
        "constraints": ["禁止把灰模静帧直接送入视频首帧槽：先经图像阶段材质升级",
                        "用电影语言复述白模的相机轨迹",
                        "预演灰模只落 00_previs/，不进候选或终版目录"],
        "question": "成片材质是否已脱离灰模低模感，站位与机位轨迹是否还原白模预演？",
        "pass_example": "精修首帧写实，站位与遮挡关系与白模一致",
        "fail_example": "成片带灰盒塑料质感；交付目录混入灰模底片",
        "rubric_items": [
            {"id": "L1-10", "repair_route": "cross_stage_rollback_stale",
             "question": "交付画面是否已完成写实或目标风格材质渲染（彻底脱离3D白模/灰盒素模质感）且空间站位合理？",
             "pass_example": "人物皮肤衣料与场景材质写实细腻，无灰盒几何块或地面辅助网格线残留",
             "fail_example": "画面直接残留未精修的3D灰模素模人偶、无纹理几何块或预演视角标尺",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
    "L1-11": {
        "title": "拟真人物 / 公众人物肖像 / 跨通道续航", "repair_route": "boost_identity_anchor",
        "constraints": ["先用最短待拍镜头跑通绑定参考哈希的真实结算探针",
                        "按目标通道过滤禁用版权词与未授权品牌名",
                        "中途换通道先出交接包并做代表镜复现核验"],
        "question": "主角面部骨相与肤色颗粒质感是否与身份基准锚点图一致、无跨镜换脸断层？",
        "pass_example": "骨相、眼距、鼻梁与肤质颗粒同基准锚点图一致",
        "fail_example": "人物脸型骨相突变为另一人，或皮肤质感骤变为失真磨皮假脸",
        "rubric_items": [
            {"id": "L1-11", "repair_route": "boost_identity_anchor",
             "question": "人物面部骨相、眼距、发际线与肤质颗粒感是否与身份基准锚点图保持同一人特征？",
             "pass_example": "正侧脸骨相与五官比例紧贴锚点图，肤色与镜头质感统一",
             "fail_example": "五官骨相明显漂移成另一张脸，或画质颗粒与锚点出现断层式假脸感",
             "requires_audio": False, "requires_motion": False, "needs_anchor": True},
        ],
    },
    "L1-12": {
        "title": "连续动作转场 / 越界穿门 / 载具接力", "repair_route": "cross_stage_rollback_stale",
        "constraints": ["载具建立实体锚（车型、配色、内饰、左右舵）并每镜首部引用",
                        "穿门写清两侧地面材质、门轴方向与可达路径，拆镜用通过 QC 的接力帧",
                        "穿屏转场以前镜最后 1 秒作为屏幕内输入源帧"],
        "question": "载具外观内饰、穿门两侧地面材质或转场画中画内容是否前后连贯守恒？",
        "pass_example": "车身涂装与内饰跨镜恒定；穿门路径物理可达；屏幕画面承接一致",
        "fail_example": "切镜后敞篷变硬顶、左舵变右舵；穿墙瞬移；拉出屏幕里变成无关壁纸",
        "rubric_items": [
            {"id": "L1-12", "repair_route": "cross_stage_rollback_stale",
             "question": "镜头中载具车型配色内饰、跨门框两侧空间连接或穿屏画面是否前后物理守恒？",
             "pass_example": "车辆涂装、车顶结构与方向盘位置全程一致；穿门动作沿真实门洞连续通过",
             "fail_example": "敞篷车中途变硬顶轿车；人物未过门洞直接穿墙换景；屏幕转场内容前后不符",
             "requires_audio": False, "requires_motion": False, "needs_anchor": False},
        ],
    },
}

ROUTE_ACTIONS = {
    "slow_or_split_shot": "拆镜：按「1 主动作 + 1 反应」拆成两镜或降速，用 OPEN ON ACTION 写起止身体端点（单变量重测）",
    "boost_identity_anchor": "提锚点：补非正面锁定视图、首句点名参考职责、去掉竞争参考，提高身份参考权重（单变量重测）",
    "cross_stage_rollback_stale": "跨阶回退：`drama_setup.py invalidate --stage character|scene|previs`，"
                                  "只作废波及白模与镜头并走增量 Human Gate #2",
    "post_clean_plate_fix": "后期修：屏幕/字幕走干净底板 + 确定性贴片，切点问题用 `assemble_cut.py --trim/--check-seams`",
}
ROUTE_ORDER = tuple(ROUTE_ACTIONS)

# --------------------------------------------------------------------------- text patterns


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


CHASE_RE = _re(r"\bchas(?:e|es|ing)\b|\bpursu\w*|\bflee\w*|\bescap\w*|追逐|追杀|逃生|对峙|打斗|攻防")
HAND_RE = _re(r"\bhands?\b|\bholding\s+(?:a|an|the|his|her|their|its|one|two)\b|\bfingers?\b|\bgrip(?:s|ping)?\b|"
              r"\bsip(?:s|ping)?\b|\bpov\b|手持|握着|握住|手指|递给|签字|进食|喝下")
ORBIT_RE = _re(r"\borbit\w*|\barc(?:s|ing)?\s+(?:shot|move|around)|over[- _]the[- _]shoulder|\bots\b|"
               r"shot[- /]reverse|reverse[- ]shot|180[- _]degree|环绕|过肩|正反打")
LIGHT_RE = _re(r"\bnight\b|\bneon\b|\bmirror\w*|\breflection\w*|\bwine\b|\bstain\w*|\brain\w*|"
               r"夜|霓虹|镜面|反射|倒影|雨|酒渍|污渍|逆光|明暗交替")
LIQUID_RE = _re(r"\bwine\b|\bstain\w*|\bspill\w*|\bblood\w*|\bsplash\w*|\bsoaked\b|酒渍|污渍|泼|血")
LIQUID_LOCK_RE = _re(r"stays? only|only on the|remains? on the (?:fabric|surface)|never (?:spreads?|turns?)|"
                     r"does not spread|仅留在|只留在|不蔓延|不会变成")
MIRROR_RE = _re(r"\bmirror\w*|\breflection\w*|镜面|倒影|反射")
MIRROR_CONTRA_RE = _re(r"faster than|slower than|opposite direction|\breverse\w*|ahead of (?:her|him|them)|反向|快于|慢于")
VEHICLE_RE = _re(r"\b(?:car|cars|vehicle|truck|van|motorcycle|motorbike|taxi|bus|convertible|sedan|suv|jeep)\b|"
                 r"汽车|轿车|跑车|载具|摩托|match[- ]cut|穿屏|画中画|screen[- ]break")
GENERIC_VEHICLE_RE = _re(r"\b(?:a|an)\s+(?:[a-z-]+\s+){0,2}(?:car|vehicle|truck|van|motorcycle|sedan|suv)\b")
WHITEMODEL_RE = _re(r"00_previs/|whitemodel|white[- ]model|gr[ae]y[- ]?box|clay render|灰模|白模")
CAMERA_VOCAB_RE = _re(r"\b(?:dolly|push(?:es)?[- ]in|pull(?:s)?[- ]back|pans?|panning|tilts?|tilting|tracking|"
                      r"tracks?|crane|orbit\w*|handheld|static|locked|zoom\w*|pedestal|camera|close-up|medium|wide|"
                      r"macro|ots|two[- ]?shot|cam_[a-z0-9_]+)\b|"
                      r"推镜|拉镜|摇镜|移镜|跟拍|升降|机位|固定镜头|固定远景|远景|中景|近景|特写")
FINAL_DIR_RE = _re(r"(?:^|/)0?2_final|(?:^|/)final|成片|交付")
MUSIC_RE = _re(r"\b(?:music|soundtrack|score|bgm|song)\b|配乐|音乐")
SUBTITLE_RE = _re(r"\bsubtitles?\b|\bcaptions?\b|字幕")

SENTENCE_SPLIT_RE = re.compile(r"[.;:。；：!?！？\n]+")
NEGATION_START_RE = _re(
    r"(?:^|[,，\s])(?:no|not|without|zero|never|avoid|free\s+of|neither)\b|"
    r"(?:无|没有|不含|不带|不出现|不做|不加|禁止?|严禁|别|零|非)"
)
POSITIVE_PIVOT_RE = _re(r"\b(?:but|with|only|while|as)\b|[但却而只仅]")
QUOTED_UI_RE = _re(r"\b(?:reading|that reads|which reads|displaying|showing)\b[^.;]{0,60}?['\"“‘]")
DEFORM_WORDS_RE = _re(r"\bmelt\w*|\bfus(?:e|es|ed|ing)\b|merg(?:e|es|ing) into|融进|缠绕|化开")
STATIC_RESULT_RE = _re(r"\b(?:standing|sitting|lying|kneeling|stands|sits|lies|kneels)\s+(?:\w+\s+){0,2}after\s+"
                       r"\w+ing\b[^,.;]*|动作完成后的静态|完成后静止")
AFTERMATH_RE = _re(r"\b(?:soaked|drenched|dripping|stained|splattered|aftermath)\b|浸透|淋湿|滴落")
EN_ACTION_VERB_RE = _re(
    r"\bkick(?:s|ed|ing)?\b|\btackl(?:e|es|ed|ing)\b|\bpunch\w*|\bslam(?:s|med|ming)?\b|\bshov\w*|"
    r"\bpush(?:es|ed|ing)?\b(?![- ]in\b)|\bgrab\w*|\bthrow\w*|\btoss\w*|\bjump\w*|\bleap\w*|"
    r"\bruns?\b|\bran\b|\brunning\b|\bsprint\w*|\bclimb\w*|\bfall(?:s|ing)?\b|\bdodg\w*|\bhandcuff\w*|"
    r"\bsearch(?:es|ed|ing)?\b|\bcalls?\b(?= backup| for)|\bstab\w*|\bshoots?\b|\bswing\w*|\bcrash\w*|\bsmash\w*|"
    r"\bdiv(?:e|es|ing)\b|\bstrik(?:e|es|ing)\b|\bspeed(?:s|ing)? away\b|\bdrives? off\b|"
    r"\bwakes?\s+up\b|\bgets?\s+dressed\b|\bwashes?\b|\bbrushes?\b|\bcooks?\b|\beats?\b|\bcleans?\s+up\b|"
    r"\bstands?\s+up\b|\bsits?\s+down\b|\bkneels?\s+down\b|\blies?\s+down\b|"
    r"\bopens?\b(?=\s+(?:the|a|an|his|her|their|its)\b)|\bcloses?\b(?=\s+(?:the|a|an|his|her|their|its)\b)|"
    r"\bshuts?\b|\bpicks?\s+up\b|\bsets?\s+down\b|\bunlocks?\b|\blocks?\b(?=\s+(?:the|a|an)\b)"
)
ZH_ACTION_VERB_RE = re.compile(
    r"踢开|扑倒|击飞|推开|抓住|抓起|跳上|跳下|冲向|冲出|跑出|摔倒|翻滚|转身逃|转身|回头|开枪|挥剑|拔刀|拔枪|上膛|"
    r"砸向|破门|推门|拉门|开门|关门|起床|穿衣|穿鞋|洗脸|刷牙|梳头|做饭|切菜|炒菜|盛饭|吃饭|喝水|收拾餐桌|收拾|"
    r"擦拭|坐下|站起|起身|跪下|拿起|放下|扔下|撕开|攀爬|翻越|跃起"
)
CJK_RE = re.compile(r"[一-鿿]")
SPEAKER_LABEL_RE = re.compile(r"[\w一-鿿]+\s*(?:（[^）]*）|\([^)]*\))?\s*[:：]")
SHOULDER_RE = _re(r"(?:behind|over)\s+(?:the\s+)?(?P<who>[a-z_]+)'s\s+shoulder")
ESCAPE_RE = _re(r"逃|\bescap\w*|\bflee\w*|run(?:s|ning)? away|甩开")
PURSUER = r"(?:\b(?:pursuer|chaser|hunter|killer|assassin)s?\b|追杀者|追兵)"
LEADING_RE = _re(PURSUER + r"[^.;]{0,30}?(?:\bruns? ahead\b|\bleads?\b|\bin front of\b|跑在前|领路)")
DOOR_RE = _re(PURSUER + r"[^.;]{0,80}?(?:holds? (?:it|the door) open|opens? the (?:exit )?door|开门)")
VIEW_ORDER = ("three_quarter", "profile", "back")

# Cross-shot anchor patterns
WARDROBE_TRANSITION_RE = _re(r"\b(?:changes?\s+into|puts?\s+on|takes?\s+off\s+(?:his|her|the)\s+(?:coat|jacket|dress|shirt))\b|换上|脱下|披上|换装")
LIGHT_TRANSITION_RE = _re(r"\b(?:turns?\s+(?:on|off)|switches?\s+(?:on|off)|light\s+shifts?|walks?\s+into)\b|开灯|关灯|灯光切换|走入光")
SPACE_TRANSITION_RE = _re(r"\b(?:walks?\s+across|crosses?\s+(?:the\s+frame|to\s+the)|moves?\s+from\s+\w+\s+to)\b|横穿|走到右侧|走到左侧|移至")

EN_COLOR_GARMENT_RE = _re(
    r"\b(?P<color>red|crimson|scarlet|blue|navy|cobalt|white|ivory|black|green|emerald|yellow|gold|grey|gray|brown|purple)\s+"
    r"(?:[a-z-]+\s+){0,2}(?P<item>coat|jacket|suit|dress|gown|shirt|blouse|hoodie|sweater|trench|uniform|robe)\b"
)
ZH_COLOR_GARMENT_RE = re.compile(
    r"(?P<color>红|深红|蓝|深蓝|白|象牙白|黑|绿|黄|灰|棕|紫)色?(?:[\u4e00-\u9fff]{0,2}?)"
    r"(?P<item>衣|风衣|大衣|外套|西装|礼服|长裙|裙|衬衫|卫衣|毛衣|制服|长袍)"
)
COLOR_CANON = {
    "crimson": "red", "scarlet": "red", "红": "red", "深红": "red",
    "navy": "blue", "cobalt": "blue", "蓝": "blue", "深蓝": "blue",
    "ivory": "white", "白": "white", "象牙白": "white",
    "黑": "black", "emerald": "green", "绿": "green",
    "gold": "yellow", "黄": "yellow", "gray": "grey", "灰": "grey",
    "棕": "brown", "紫": "purple",
}
LIGHT_LEFT_RE = _re(r"\b(?:key\s+light|rim\s+light|main\s+light|side\s+light|lit|lamp|sunlight|moonlight)[^,.;]{0,24}\bfrom\s+(?:the\s+)?(?:frame[- ]|screen[- ])?left\b|"
                    r"\b(?:frame[- ]|screen[- ])?left\s+(?:key\s+|rim\s+|main\s+|side\s+)?light\b|左侧?主光|左光|左侧光|主光从左|左上方?主光|从画面左侧照")
LIGHT_RIGHT_RE = _re(r"\b(?:key\s+light|rim\s+light|main\s+light|side\s+light|lit|lamp|sunlight|moonlight)[^,.;]{0,24}\bfrom\s+(?:the\s+)?(?:frame[- ]|screen[- ])?right\b|"
                     r"\b(?:frame[- ]|screen[- ])?right\s+(?:key\s+|rim\s+|main\s+|side\s+)?light\b|右侧?主光|右光|右侧光|主光从右|右上方?主光|从画面右侧照")
LIGHT_WARM_RE = _re(r"\bwarm\s+(?:amber|tungsten|golden)\s+(?:key\s+)?light\b|暖(?:黄|琥珀|钨丝)?主?光")
LIGHT_COLD_RE = _re(r"\b(?:cold|cool|icy)\s+(?:blue|cyan|neon)\s+(?:key\s+)?light\b|冷(?:蓝|青|白)?主?光")
SIDE_LEFT_RE = _re(r"\b(?:on\s+(?:the\s+)?(?:frame|screen)[- ]left|at\s+(?:frame|screen)[- ]left|left\s+side\s+of\s+(?:the\s+)?frame|stands?\s+on\s+the\s+left)\b|"
                   r"左侧站位|左位|画面左侧|站在左侧|居左")
SIDE_RIGHT_RE = _re(r"\b(?:on\s+(?:the\s+)?(?:frame|screen)[- ]right|at\s+(?:frame|screen)[- ]right|right\s+side\s+of\s+(?:the\s+)?frame|stands?\s+on\s+the\s+right)\b|"
                    r"右侧站位|右位|画面右侧|站在右侧|居右")


def _is_negated_span(sentence: str, start: int) -> bool:
    prefix = sentence[:start]
    neg_matches = list(NEGATION_START_RE.finditer(prefix))
    if not neg_matches:
        return False
    tail = prefix[neg_matches[-1].end():]
    if POSITIVE_PIVOT_RE.search(tail):
        return False
    # Allow coordinated negated lists ("无环绕、无镜面反射", "without orbit or reflection", "no A, no B"),
    # while breaking negation at an un-negated comma clause that introduces a new subject/verb.
    if re.search(r"[,，]", tail):
        after_comma = re.split(r"[,，]", tail)[-1]
        if not re.fullmatch(r"[\s、和与及或norand]*", after_comma, re.IGNORECASE):
            return False
    return True


def positive_mention(pattern: re.Pattern[str], text: str) -> bool:
    """True when at least one match is not inside a negation scope."""
    offset = 0
    for chunk in SENTENCE_SPLIT_RE.split(text):
        pos = text.find(chunk, offset)
        offset = pos + len(chunk) if pos >= 0 else offset
        for match in pattern.finditer(chunk):
            if not _is_negated_span(chunk, match.start()):
                return True
    return False


def strip_negated_clauses(text: str) -> str:
    """Remove negated spans before counting affirmative action events."""
    kept: list[str] = []
    for chunk in SENTENCE_SPLIT_RE.split(text):
        sub_kept = []
        for sub in re.split(r"[,，]", chunk):
            if not NEGATION_START_RE.search(sub):
                sub_kept.append(sub)
        if sub_kept:
            kept.append("，".join(sub_kept))
    return "。".join(kept)


# --------------------------------------------------------------------------- normalisation & schema


def finite_positive(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_props_state(shot: dict[str, Any]) -> bool:
    props = shot.get("props_state")
    if not isinstance(props, dict):
        return False
    return any(isinstance(props.get(k), dict) and bool(props.get(k)) for k in ("in", "out"))


def classify_mode(body: dict[str, Any]) -> str:
    if not body:
        return "empty"
    if "nbp_version" in body or {"characters", "camera", "references"} <= set(body):
        return "nbp"
    has_shot_keys = any(k in body for k in ("shot_id", "id", "prompt", "duration_s", "duration", "curr_shot"))
    has_workflow_keys = (
        (isinstance(body.get("workflow_state"), dict) and bool(body["workflow_state"]))
        or (isinstance(body.get("project_state"), dict) and bool(body["project_state"]))
        or nonempty_str(body.get("agent_proposed_action"))
    )
    if not has_shot_keys and has_workflow_keys:
        return "workflow_case"
    if has_shot_keys:
        return "shot"
    return "empty"


def nbp_to_shot(body: dict[str, Any]) -> tuple[dict[str, Any], str]:
    from validate_nbp_prompt import V2_IMAGE_FORBIDDEN, validate_prompt

    is_img = ("duration" not in body and "audio" not in body
              and not (set(body) & V2_IMAGE_FORBIDDEN) and "aspect_ratio" in body)
    ptype = "image" if is_img else "video"
    errors, _, _, _ = validate_prompt(body, ptype)
    camera = body.get("camera")
    cam_text = (" ".join(str(v) for v in camera.values() if nonempty_str(v))
                if isinstance(camera, dict) else str(camera or ""))
    chars = body.get("characters") if isinstance(body.get("characters"), list) else []
    actors = [str(c.get("name") or c.get("ref") or f"c{i}") for i, c in enumerate(chars) if isinstance(c, dict)]
    refs = [str(r.get("ref")) for r in (body.get("references") or []) if isinstance(r, dict) and nonempty_str(r.get("ref"))]
    dur_block = body.get("duration")
    dur = (dur_block.get("target_s") if isinstance(dur_block, dict)
           else (1.0 if ptype == "image" else dur_block))
    prompt_parts = [str(body.get(k) or "") for k in ("subject", "scene", "action", "motion", "light", "style")]
    shot: dict[str, Any] = {
        "shot_id": str(body.get("shot_id") or "NBP_SHOT"),
        "duration_s": dur,
        "actors": actors,
        "actor_count": len(actors),
        "refs": refs,
        "camera_move": cam_text,
        "audio": body.get("audio") if isinstance(body.get("audio"), dict) else {},
        "beats": body.get("beats") if isinstance(body.get("beats"), list) else [],
        "prompt": " ".join(part.strip() for part in [*prompt_parts, cam_text] if part and part.strip()),
        "_nbp_errors": [f"NBP_SCHEMA_INVALID:{err}" for err in errors],
    }
    return shot, ptype


def unwrap_case(payload: object) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """(mode, shot, context) from a regression case, NBP object, workflow case, or project shot row."""
    if not isinstance(payload, dict):
        raise ValueError("case input must be a JSON object")
    raw_body = payload.get("synthetic_input_prompt_or_spec", payload)
    if not isinstance(raw_body, dict):
        return "empty", {}, {}
    mode = classify_mode(raw_body)
    if mode == "nbp":
        shot, _ = nbp_to_shot(raw_body)
        context: dict[str, Any] = {
            "release_intent": payload.get("release_intent") or {},
            "l1_injected": payload["l1_injected"] if "l1_injected" in payload else raw_body.get("l1_injected", _MISSING),
            "has_explicit_l1_injected": "l1_injected" in payload or "l1_injected" in raw_body,
        }
        return mode, shot, context
    curr = raw_body.get("curr_shot")
    if curr is not None and not isinstance(curr, dict):
        return "empty", {}, {}
    shot = dict(curr) if isinstance(curr, dict) else dict(raw_body)
    context = {key: raw_body.get(key) for key in ("workflow_state", "project_state", "prev_shot", "user_request",
                                                  "agent_proposed_action", "narrative_promise", "scene_id", "creative_mode")}
    context["release_intent"] = raw_body.get("release_intent") or shot.get("release_intent") or {}
    has_inj = "l1_injected" in payload or "l1_injected" in raw_body or "l1_injected" in shot
    inj_val = (payload["l1_injected"] if "l1_injected" in payload
               else (raw_body["l1_injected"] if "l1_injected" in raw_body else shot.get("l1_injected", _MISSING)))
    context["l1_injected"] = inj_val
    context["has_explicit_l1_injected"] = has_inj
    context["narrative_promise"] = context["narrative_promise"] or shot.get("narrative_promise")
    if "shot_id" not in shot and nonempty_str(shot.get("id")):
        shot["shot_id"] = shot["id"]
    if "duration_s" not in shot and "duration" in shot:
        shot["duration_s"] = shot["duration"]
    return mode, shot, context


_MISSING = object()


def actor_total(shot: dict[str, Any]) -> int:
    count = shot.get("actor_count")
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    actors = shot.get("actors")
    return len(actors) if isinstance(actors, list) else 0


def has_subject_or_anchor_slot(shot: dict[str, Any]) -> bool:
    if isinstance(shot.get("actors"), list) and len(shot["actors"]) > 0:
        return True
    if isinstance(shot.get("refs"), list) and any(nonempty_str(r) for r in shot["refs"]):
        return True
    if (nonempty_str(shot.get("subject")) or nonempty_str(shot.get("first_frame_ref"))
            or nonempty_str(shot.get("scene")) or nonempty_str(shot.get("previs_ref"))):
        return True
    count = shot.get("actor_count")
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        return (count > 0 or nonempty_str(shot.get("camera")) or nonempty_str(shot.get("camera_move"))
                or nonempty_str(shot.get("beat")) or bool(CAMERA_VOCAB_RE.search(str(shot.get("prompt") or ""))))
    return False


def dialogue_beats(shot: dict[str, Any]) -> list[dict[str, Any]]:
    return [beat for beat in shot.get("beats") or [] if isinstance(beat, dict)
            and (beat.get("speakers") or beat.get("dialogue") or beat.get("say"))]


def has_dialogue(shot: dict[str, Any]) -> bool:
    audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
    line = shot.get("line")
    return bool(dialogue_beats(shot) or audio.get("dialogue")
                or (isinstance(line, str) and line.strip())
                or (isinstance(line, list) and any(nonempty_str(x) for x in line)))


def action_events(prompt: str) -> int:
    """Total affirmative discrete action events across the entire shot (EN + ZH)."""
    cleaned = strip_negated_clauses(STATIC_RESULT_RE.sub(" ", prompt))
    en_hits = EN_ACTION_VERB_RE.findall(cleaned)
    zh_hits = ZH_ACTION_VERB_RE.findall(cleaned)
    return len(en_hits) + len(zh_hits)


def action_budget(duration: float) -> int:
    """Maximum discrete action events readable in `duration` seconds."""
    if duration < 3.0:
        return 1
    return 2 + max(0, int((duration - 3.5) // 2.5))


# --------------------------------------------------------------------------- cross-shot anchors


def _extract_wardrobe_colors(shot: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    explicit = shot.get("wardrobe") or shot.get("wardrobe_state")
    if isinstance(explicit, dict):
        for who, desc in explicit.items():
            if nonempty_str(who) and nonempty_str(desc):
                out.setdefault(who.strip().lower(), set()).add(desc.strip().lower())
    elif nonempty_str(explicit):
        key = (shot.get("actors") or ["_lead"])[0] if isinstance(shot.get("actors"), list) and shot.get("actors") else "_lead"
        out.setdefault(str(key).lower(), set()).add(str(explicit).strip().lower())
    prompt = str(shot.get("prompt") or "")
    actors = [str(a).lower() for a in (shot.get("actors") or []) if nonempty_str(a)]
    default_actor = actors[0] if len(actors) == 1 else "_shared"
    for match in EN_COLOR_GARMENT_RE.finditer(prompt):
        color = COLOR_CANON.get(match.group("color").lower(), match.group("color").lower())
        out.setdefault(default_actor, set()).add(color)
    for match in ZH_COLOR_GARMENT_RE.finditer(prompt):
        color = COLOR_CANON.get(match.group("color"), match.group("color"))
        out.setdefault(default_actor, set()).add(color)
    return out


def _extract_light_signature(shot: dict[str, Any]) -> set[str]:
    text = (f"{shot.get('lighting') or ''} {shot.get('lighting_direction') or ''} "
            f"{shot.get('key_light') or ''} {shot.get('prompt') or ''}")
    tags: set[str] = set()
    if positive_mention(LIGHT_LEFT_RE, text):
        tags.add("dir:left")
    if positive_mention(LIGHT_RIGHT_RE, text):
        tags.add("dir:right")
    if positive_mention(LIGHT_WARM_RE, text):
        tags.add("temp:warm")
    if positive_mention(LIGHT_COLD_RE, text):
        tags.add("temp:cold")
    return tags


def _extract_side_signature(shot: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    explicit = (shot.get("spatial_anchor") or shot.get("spatial_side")
                or shot.get("screen_side") or shot.get("actor_positions"))
    actors = [str(a).lower() for a in (shot.get("actors") or []) if nonempty_str(a)]
    default_actor = actors[0] if len(actors) == 1 else "_shared"
    if isinstance(explicit, dict):
        for who, side in explicit.items():
            if nonempty_str(who) and nonempty_str(side):
                s = str(side).lower()
                if "left" in s or "左" in s:
                    out[who.lower()] = "left"
                elif "right" in s or "右" in s:
                    out[who.lower()] = "right"
    elif nonempty_str(explicit):
        s = str(explicit).lower()
        if "left" in s or "左" in s:
            out[default_actor] = "left"
        elif "right" in s or "右" in s:
            out[default_actor] = "right"
    prompt = str(shot.get("prompt") or "")
    has_l = positive_mention(SIDE_LEFT_RE, prompt)
    has_r = positive_mention(SIDE_RIGHT_RE, prompt)
    if has_l and not has_r:
        out.setdefault(default_actor, "left")
    elif has_r and not has_l:
        out.setdefault(default_actor, "right")
    return out


def _same_scene(prev: dict[str, Any], curr: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if nonempty_str(ctx.get("scene_id")):
        return True
    from shot_invariants import shot_scene_key
    ps = shot_scene_key({**prev, "id": prev.get("shot_id") or prev.get("id") or ""})
    cs = shot_scene_key({**curr, "id": curr.get("shot_id") or curr.get("id") or ""})
    if ps and cs:
        return ps == cs
    return prev.get("scene") == curr.get("scene")


def check_cross_shot_anchors(shot: dict[str, Any], ctx: dict[str, Any]) -> list[tuple[str, str]]:
    prev = ctx.get("prev_shot")
    if not isinstance(prev, dict) or not prev:
        return []
    if shot.get("continuity_break") is True or shot.get("intentional_change") is True:
        return []
    if shot.get("continuity_mode") == "editorial_cut" and shot.get("allow_anchor_reset") is True:
        return []
    if not _same_scene(prev, shot, ctx):
        return []
    prompt = str(shot.get("prompt") or "")
    found: list[tuple[str, str]] = []
    if not WARDROBE_TRANSITION_RE.search(prompt):
        w_prev, w_curr = _extract_wardrobe_colors(prev), _extract_wardrobe_colors(shot)
        for who in sorted(set(w_prev) & set(w_curr)):
            if w_prev[who] and w_curr[who] and w_prev[who].isdisjoint(w_curr[who]):
                found.append(("L0", f"WARDROBE_CONTINUITY_CONFLICT:{who}:{sorted(w_prev[who])[0]}!={sorted(w_curr[who])[0]}"))
    if not LIGHT_TRANSITION_RE.search(prompt):
        l_prev, l_curr = _extract_light_signature(prev), _extract_light_signature(shot)
        if (("dir:left" in l_prev and "dir:right" in l_curr and "dir:left" not in l_curr)
                or ("dir:right" in l_prev and "dir:left" in l_curr and "dir:right" not in l_curr)
                or ("temp:warm" in l_prev and "temp:cold" in l_curr and "temp:warm" not in l_curr)
                or ("temp:cold" in l_prev and "temp:warm" in l_curr and "temp:cold" not in l_curr)):
            found.append(("L1-04", f"LIGHTING_ANCHOR_CONFLICT:{','.join(sorted(l_prev))}!={','.join(sorted(l_curr))}"))
    axis = shot.get("previs_axis_check") if isinstance(shot.get("previs_axis_check"), dict) else {}
    if axis.get("allow_axis_cross") is not True and not SPACE_TRANSITION_RE.search(prompt):
        s_prev, s_curr = _extract_side_signature(prev), _extract_side_signature(shot)
        for who in sorted(set(s_prev) & set(s_curr)):
            if s_prev[who] != s_curr[who]:
                found.append(("L1-03", f"SPATIAL_ANCHOR_CONFLICT:{who}:{s_prev[who]}!={s_curr[who]}"))
    return found


# --------------------------------------------------------------------------- triggers


def trigger_map(shot: dict[str, Any], ctx: dict[str, Any]) -> dict[str, bool]:
    prompt = str(shot.get("prompt") or "")
    camera = f"{prompt} {shot.get('camera_move') or ''}"
    state = ctx.get("project_state") or {}
    flow = ctx.get("workflow_state") or {}
    intent = ctx.get("release_intent") or {}
    refs = " ".join(str(ref) for ref in shot.get("refs") or [])
    raw_dur = shot.get("duration_s")
    duration = float(raw_dur) if finite_positive(raw_dur) else 0.0
    events = action_events(prompt)
    gates = [flow.get("human_gate_1_confirmed"), shot.get("human_gate_1_confirmed"), shot.get("script_locked"),
             flow.get("script_locked")]
    return {
        "L1-01": actor_total(shot) >= 2 or positive_mention(CHASE_RE, prompt),
        "L1-02": nonempty_props_state(shot) or positive_mention(HAND_RE, prompt),
        "L1-03": ("previs_axis_check" in shot or "available_actor_views" in shot
                  or positive_mention(ORBIT_RE, camera)),
        "L1-04": positive_mention(LIGHT_RE, prompt) or bool(_extract_light_signature(shot) & _extract_light_signature(ctx.get("prev_shot") or {})),
        "L1-05": (shot.get("screen_ui") not in (None, "none")
                  or (nonempty_str(prompt) and mentions_screen_or_ui({
                      "prompt": re.sub(r"\bscreen[- ](?:left|right|direction)\b", "frame-side", prompt, flags=re.I),
                      "line": shot.get("line", ""),
                  }))),
        "L1-06": ((duration > 0 and events > action_budget(duration))
                  or bool(STATIC_RESULT_RE.search(prompt))
                  or (duration >= 8 and actor_total(shot) >= 1 and positive_mention(AFTERMATH_RE, prompt))),
        "L1-07": has_dialogue(shot) or bool(intent.get("lexicon")) or positive_mention(MUSIC_RE, prompt),
        "L1-08": bool(state.get("changed_asset") or state.get("previous_asset") or shot.get("stale_upstream")),
        "L1-09": (bool(flow) and (flow.get("human_gate_1_confirmed") is not True
                                  or any(flow.get(k) in (None, "") for k in ("image_model", "video_model")))
                  or any(value is False for value in gates) or bool(ctx.get("model_gate_errors"))),
        "L1-10": bool(WHITEMODEL_RE.search(f"{shot.get('first_frame_ref') or ''} {refs} {prompt}")),
        "L1-11": (state.get("real_public_figures") is True or intent.get("real_public_figures") is True
                  or bool(shot.get("public_figure_likeness") or shot.get("provider_switch"))),
        "L1-12": positive_mention(VEHICLE_RE, prompt) or "vehicle_anchor_locked" in shot,
    }


# --------------------------------------------------------------------------- checks (rule id, code)


def schema_and_l0_checks(mode: str, shot: dict[str, Any], ctx: dict[str, Any]) -> list[tuple[str, str]]:
    if mode == "empty":
        return [("L0", "SCHEMA_EMPTY_OR_UNRECOGNIZED")]
    if mode == "workflow_case":
        return []
    found: list[tuple[str, str]] = [("L0", code) for code in shot.get("_nbp_errors") or []]
    if not nonempty_str(shot.get("shot_id")):
        found.append(("L0", "SHOT_SCHEMA_INCOMPLETE:shot_id"))
    prompt = shot.get("prompt")
    if shot.get("_raw_prompt_missing") is True or not nonempty_str(prompt):
        found.append(("L0", "SHOT_SCHEMA_INCOMPLETE:prompt"))
    duration = shot.get("duration_s")
    if not finite_positive(duration):
        found.append(("L0", "SHOT_SCHEMA_INCOMPLETE:duration_s"))
    if mode == "shot" and not has_subject_or_anchor_slot(shot):
        found.append(("L0", "SHOT_SCHEMA_INCOMPLETE:subject_or_anchor"))
    if "props_state" in shot:
        for err in check_props_state({**shot, "id": str(shot.get("shot_id") or "shot")}):
            found.append(("L0", err))
    if nonempty_str(prompt):
        count = shot.get("actor_count")
        if isinstance(count, int) and not isinstance(count, bool):
            crowd = shot.get("crowd_count") if isinstance(shot.get("crowd_count"), int) and not isinstance(shot.get("crowd_count"), bool) else 0
            over = [n for n in detected_headcounts(prompt) if n > count + crowd]
            if over:
                found.append(("L0-05", f"PROMPT_HEADCOUNT_EXCEEDS_ACTORS:{max(over)}>{count + crowd}"))
        if positive_mention(SUBTITLE_RE, prompt):
            found.append(("L0-04", "BAKED_SUBTITLE_REQUEST_FORBIDDEN"))
    found += check_cross_shot_anchors(shot, ctx)
    return found


def check_l1_01(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    prompt = str(shot.get("prompt") or "")
    promise = f"{ctx.get('narrative_promise') or ''} {prompt}"
    if not positive_mention(ESCAPE_RE, promise):
        return []
    parts = (["leading"] if LEADING_RE.search(prompt) else []) + (["opening_door"] if DOOR_RE.search(prompt) else [])
    return [f"CHASE_VECTOR_INVERSION:pursuer_{'_and_'.join(parts)}"] if parts else []


def check_l1_02(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    errors = [] if not DEFORM_WORDS_RE.search(str(shot.get("prompt") or "")) else ["HAND_PROP_DEFORMATION_WORDING"]
    prev = ctx.get("prev_shot")
    if isinstance(prev, dict) and (prev.get("shot_id") or prev.get("id")) and shot.get("shot_id"):
        pid = prev.get("shot_id") or prev.get("id")
        rows = [{**prev, "id": pid}, {**shot, "id": shot["shot_id"]}]
        errors += check_props_continuity(rows)
    return errors


def check_l1_03(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    views = (shot.get("available_actor_views") if isinstance(shot.get("available_actor_views"), dict)
             else (ctx.get("project_actor_views") if isinstance(ctx.get("project_actor_views"), dict) else {}))
    camera = f"{shot.get('prompt') or ''} {shot.get('camera_move') or ''}"
    for who in sorted({m["who"].lower() for m in SHOULDER_RE.finditer(camera)}):
        if who in views:
            missing = [view for view in VIEW_ORDER[1:] if view not in (views.get(who) or [])]
            if missing:
                errors.append(f"MISSING_REQUIRED_ACTOR_VIEWS:{who}:{','.join(missing)}")
    axis = shot.get("previs_axis_check") if isinstance(shot.get("previs_axis_check"), dict) else {}
    if axis.get("axis_180_crossed") is True and axis.get("allow_axis_cross") is not True:
        errors.append("AXIS_180_CROSSED_UNALLOWED")
    return errors


def check_l1_04(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    prompt = str(shot.get("prompt") or "")
    errors = []
    if positive_mention(LIQUID_RE, prompt) and actor_total(shot) >= 1 and not LIQUID_LOCK_RE.search(prompt):
        errors.append("LIQUID_STAIN_MATERIAL_LOCK_MISSING")
    if positive_mention(MIRROR_RE, prompt) and MIRROR_CONTRA_RE.search(prompt):
        errors.append("MIRROR_REFLECTION_PHYSICS_CONTRADICTION")
    return errors


def check_l1_05(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    prompt = str(shot.get("prompt") or "")
    ui_prompt = re.sub(r"\bscreen[- ](?:left|right|direction)\b", "frame-side", prompt, flags=re.I)
    mentioned = mentions_screen_or_ui({"prompt": ui_prompt, "line": shot.get("line", "")})
    errors = ["SCREEN_UI_REQUIRED"] if mentioned and "screen_ui" not in shot else []
    if "screen_ui" in shot and shot.get("screen_ui") not in ("none", "clean_plate_post_replace"):
        errors.append("RAW_SCREEN_UI_TEXT_FORBIDDEN")
    if mentioned and QUOTED_UI_RE.search(prompt):
        errors.append("RAW_SCREEN_UI_TEXT_FORBIDDEN")
    return errors


def check_l1_06(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    prompt = str(shot.get("prompt") or "")
    raw_dur = shot.get("duration_s")
    duration = float(raw_dur) if finite_positive(raw_dur) else 0.0
    errors = []
    events = action_events(prompt)
    if duration > 0 and events > action_budget(duration):
        errors.append(f"ACTION_DENSITY_OVERLOAD:{events}_EVENTS_IN_{duration:g}S")
    if STATIC_RESULT_RE.search(prompt) and "open on action" not in prompt.lower():
        errors.append("STATIC_RESULT_OPENING_INSTEAD_OF_OPEN_ON_ACTION")
    if duration >= 8 and actor_total(shot) >= 1 and positive_mention(AFTERMATH_RE, prompt) and not LIQUID_LOCK_RE.search(prompt):
        errors.append("STATIC_AFTER_EVENT_LONG_DRIFT_RISK")
    return errors


def dialogue_text(shot: dict[str, Any]) -> str:
    audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
    lines = [str(beat.get("dialogue") or beat.get("say") or "") for beat in dialogue_beats(shot)]
    lines += [str(item) for item in audio.get("dialogue") or []]
    line = shot.get("line")
    lines += line if isinstance(line, list) else ([str(line)] if line else [])
    return "\n".join(lines)


def lexicon_errors(lexicon: list[Any], text: str) -> list[str]:
    errors = []
    for entry in lexicon if isinstance(lexicon, list) else []:
        for variant in (entry.get("forbidden_variants") or []) if isinstance(entry, dict) else []:
            pattern = rf"\b{re.escape(variant)}\b" if variant.isascii() else re.escape(variant)
            if re.search(pattern, text, re.IGNORECASE if variant.isascii() else 0):
                errors.append(f"LEXICON_VARIANT_FORBIDDEN:{variant}")
    return errors


def check_l1_07(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    intent = ctx.get("release_intent") or {}
    audio = shot.get("audio") if isinstance(shot.get("audio"), dict) else {}
    prompt = str(shot.get("prompt") or "")
    errors = ["MULTI_SPEAKER_IN_SINGLE_BEAT"] if any(len(b.get("speakers") or []) > 1
                                                    for b in dialogue_beats(shot)) else []
    spoken = SPEAKER_LABEL_RE.sub(" ", dialogue_text(shot))
    language = intent.get("target_language")
    if spoken.strip() and language and (CJK_RE.search(spoken) is None) == (language == "zh"):
        errors.append(f"DIALOGUE_LANGUAGE_MISMATCH:expected={language}")
    errors += lexicon_errors(intent.get("lexicon"), f"{dialogue_text(shot)}\n{prompt}")
    if (intent.get("native_bgm") is False or audio.get("native_bgm") is False) and positive_mention(MUSIC_RE, prompt):
        errors.append("NATIVE_BGM_CONFLICT_WITH_RELEASE_INTENT")
    ends = [float(b["end_s"]) for b in dialogue_beats(shot) if finite_positive(b.get("end_s"))]
    duration = shot.get("duration_s")
    if ends and finite_positive(duration) and float(duration) - max(ends) < 0.6:
        errors.append("DIALOGUE_TAIL_MARGIN_INSUFFICIENT")
    return errors


def check_l1_08(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    state = ctx.get("project_state") or {}
    downstream = {sid for key, value in state.items() if key.startswith("downstream_shots") for sid in value or []}
    errors = []
    if downstream - set(state.get("stale_marked_shots") or []) or shot.get("stale_upstream"):
        errors.append("DOWNSTREAM_STALE_INVALIDATION_MISSING")
    if state.get("incremental_human_gate_2_confirmed") is False or shot.get("pending_gate2"):
        errors.append("INCREMENTAL_HUMAN_GATE_2_REQUIRED")
    return errors


def check_l1_09(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    flow = {**(ctx.get("workflow_state") or {}), **{k: shot[k] for k in ("human_gate_1_confirmed", "script_locked")
                                                    if k in shot}}
    errors = ["HUMAN_GATE_1_NOT_CONFIRMED"] if flow.get("human_gate_1_confirmed") is False else []
    keys = ("image_model", "video_model", "audio_plan", "aspect_ratio")
    if any(key in flow and flow[key] in (None, "") for key in keys):
        errors.append("MODEL_AND_SPEC_UNSPECIFIED")
    if flow.get("script_locked") is False:
        errors.append("SCRIPT_NOT_LOCKED")
    return errors + list(ctx.get("model_gate_errors") or [])


def check_l1_10(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    errors = []
    first = str(shot.get("first_frame_ref") or "")
    if WHITEMODEL_RE.search(first) and shot.get("first_frame_upgraded") is not True:
        errors.append("RAW_WHITEMODEL_USED_AS_FIRST_FRAME")
    cam_text = f"{shot.get('prompt') or ''} {shot.get('camera_move') or ''} {shot.get('camera') or ''}"
    if nonempty_str(shot.get("prompt")) and not CAMERA_VOCAB_RE.search(cam_text):
        errors.append("CAMERA_PATH_NOT_RESTATED_FROM_PREVIS")
    if FINAL_DIR_RE.search(str(shot.get("output_target_dir") or "")):
        errors.append("PREVIS_OR_UNAPPROVED_TARGET_IN_FINAL_DIR")
    return errors


def check_l1_11(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    state = ctx.get("project_state") or {}
    return (["LIKENESS_PROBE_INVALIDATED_AFTER_ASSET_RELOCK"]
            if state.get("real_public_figures") is True and state.get("probe_take_ref_sha256_matches_current") is False
            else [])


def check_l1_12(shot: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    locked = shot.get("vehicle_anchor_locked")
    prompt = str(shot.get("prompt") or "")
    if locked is False or (locked is None and GENERIC_VEHICLE_RE.search(prompt)):
        return ["VEHICLE_ENTITY_ANCHOR_MISSING"]
    return []


L1_CHECKS = {"L1-01": check_l1_01, "L1-02": check_l1_02, "L1-03": check_l1_03, "L1-04": check_l1_04,
             "L1-05": check_l1_05, "L1-06": check_l1_06, "L1-07": check_l1_07, "L1-08": check_l1_08,
             "L1-09": check_l1_09, "L1-10": check_l1_10, "L1-11": check_l1_11, "L1-12": check_l1_12}


# --------------------------------------------------------------------------- declarative custom rules


def valid_custom_detector(detector: object) -> bool:
    if not isinstance(detector, dict):
        return False
    triggers = detector.get("trigger_any")
    if not isinstance(triggers, list) or not triggers or any(not nonempty_str(t) for t in triggers):
        return False
    has_check = (
        (isinstance(detector.get("forbid_any"), list) and any(nonempty_str(x) for x in detector["forbid_any"]))
        or (isinstance(detector.get("require_any"), list) and any(nonempty_str(x) for x in detector["require_any"]))
    )
    if not has_check or not nonempty_str(detector.get("error_code")):
        return False
    rubric = detector.get("rubric")
    if rubric is not None:
        if not isinstance(rubric, dict):
            return False
        if not all(nonempty_str(rubric.get(k)) for k in ("question", "pass_example", "fail_example", "repair_route")):
            return False
        if rubric.get("repair_route") not in ROUTE_ACTIONS:
            return False
    return True


def custom_rules_of(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    custom: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid = str(row.get("rule_id") or "")
        if row.get("status") != "ACTIVE" or not rid or rid in L1_RULES:
            continue
        det = row.get("detector")
        if valid_custom_detector(det):
            custom[rid] = {
                "title": str(row.get("title") or rid),
                "constraints": [str(row.get("remediation_rule") or "")],
                "question": str((det.get("rubric") or {}).get("question") or row.get("post_gen_focus") or ""),
                "detector": det,
            }
    return custom


def run_custom_rule(spec: dict[str, Any], shot: dict[str, Any]) -> tuple[bool, list[str]]:
    det = spec["detector"]
    prompt = f"{shot.get('prompt') or ''} {shot.get('camera_move') or ''}"
    trig_re = _re("|".join(re.escape(str(tok)) for tok in det["trigger_any"]))
    if not positive_mention(trig_re, prompt):
        return False, []
    errors: list[str] = []
    forbid = [str(x) for x in (det.get("forbid_any") or []) if nonempty_str(x)]
    if forbid and positive_mention(_re("|".join(re.escape(x) for x in forbid)), prompt):
        errors.append(str(det["error_code"]))
    require = [str(x) for x in (det.get("require_any") or []) if nonempty_str(x)]
    if require and not _re("|".join(re.escape(x) for x in require)).search(prompt):
        errors.append(str(det["error_code"]))
    return True, list(dict.fromkeys(errors))


def injection_errors(injected: object, has_explicit: bool, require_injection: bool,
                     triggered: list[str]) -> list[tuple[str, str]]:
    """Verify exact L1 mount set when `l1_injected` is explicitly supplied or required by production compile."""
    if not has_explicit and not require_injection:
        return []
    if not isinstance(injected, list) or any(not nonempty_str(x) for x in injected):
        return [("L1", f"L1_INJECTION_MISSING:{rule}") for rule in (triggered or ["INVALID_LIST"])]
    given = {str(item).strip() for item in injected}
    return ([("L1", f"L1_INJECTION_MISSING:{rule}") for rule in triggered if rule not in given]
            + [("L1", f"L1_INJECTION_UNTRIGGERED:{rule}") for rule in sorted(given - set(triggered))])


def compile_guardrail_prompt(base_prompt: str, triggered_l1_rules: list[str],
                             custom_rules: dict[str, dict[str, Any]] | None = None) -> tuple[str, list[str]]:
    """Deterministically compile L0 baseline + exact triggered L1 constraints into an adapter prompt."""
    mounted = list(dict.fromkeys(triggered_l1_rules))
    clauses = ["no baked-in subtitles, no watermarks, no garbled AI text, no extra/fused fingers, no dead black flash"]
    for rid in mounted:
        if rid in L1_RULES:
            clauses.append(f"[{rid}] {L1_RULES[rid]['constraints'][0]}")
        elif custom_rules and rid in custom_rules:
            clauses.append(f"[{rid}] {custom_rules[rid]['constraints'][0]}")
    compiled = f"{base_prompt.strip()} Guardrails: {'; '.join(clauses)}."
    return compiled, mounted


def craft_checks(shot, creative_mode):
    """Inspect the spoken line separately from scene notes and editorial instructions."""
    errors, warnings = [], []
    words = "\n".join(str(v) for v in (dialogue_text(shot), shot.get("dialogue"), shot.get("zh")) if v)
    quoted = re.findall(r"(?:says?|asks?|whispers?|台词|说道?|问道?)\s*[:：,，]?\s*[\"“「]([^\"”」]+)[\"”」]",
                        str(shot.get("prompt", "")), re.I)
    words += "\n" + "\n".join(quoted)
    if re.search(r"上集|下集|本集|第(?:几|[零一二三四五六七八九十\d]+)集|观众朋友们|各位观众", words):
        errors.append("META_DIALOGUE_BREAKS_FOURTH_WALL")
    text = json.dumps(shot, ensure_ascii=False)
    if re.search(r"无工牌|未佩戴工牌|没有(?:工作牌|工牌)", text) and re.search(r"bare[- ]chested|shirtless|naked torso", text, re.I):
        errors.append("MISSING_BADGE_MISTRANSLATION")
    if re.search(r"behind (?:the |his |her )?back|in(?:side)? (?:a |the |his |her )?pocket|off[- ]?screen|背后|口袋|画外", text, re.I) and re.search(r"grip|regrasp|换手|握紧|松手|换握", text, re.I):
        warnings.append("OCCLUDED_LIMB_ACTION")
    duration = shot.get("duration_s", shot.get("duration"))
    if (creative_mode == "short_drama" and not words.strip() and not shot.get("beats")
            and isinstance(duration, (int, float)) and duration > 5 and not shot.get("intentional_hold")):
        warnings.append("SILENT_HOLD_PACING_REVIEW")
    if creative_mode == "short_drama" and (words.strip() or shot.get("beats")):
        if not (shot.get("open_on_action") or re.search("open on action|开场动作", text, re.I)):
            warnings.append("OPEN_ON_ACTION_REVIEW")
        if not shot.get("escalation"):
            warnings.append("ESCALATION_REVIEW")
        for beat in shot.get("beats") or []:
            if not isinstance(beat, dict) or not (beat.get("dialogue") or beat.get("say")):
                continue
            if beat.get("knowledge_violation") or beat.get("knowledge") == "unknown_to_speaker":
                errors.append("SPEAKER_KNOWLEDGE_VIOLATION")
            elif not all(beat.get(k) for k in ("speaker", "listener", "knowledge")):
                warnings.append("DIALOGUE_KNOWLEDGE_BOUNDARY_REVIEW")
    return errors, list(dict.fromkeys(warnings))


def evaluate(payload: dict[str, Any], active_rules: set[str] | None = None,
             extra_context: dict[str, Any] | None = None,
             book_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pre-Gen verdict of one shot, NBP prompt, or workflow regression case."""
    mode, shot, ctx = unwrap_case(payload)
    extra = extra_context or {}
    ctx = {**ctx, **{k: v for k, v in extra.items() if k not in ("require_l1_injection",)}}
    custom = custom_rules_of(book_rows or [])
    default_active = set(L1_RULES) | set(custom)
    active = default_active if active_rules is None else set(active_rules)
    hits = trigger_map(shot, ctx) if mode != "empty" else {r: False for r in L1_RULES}
    triggered = [rule for rule in L1_RULES if hits.get(rule) and rule in active]
    found = schema_and_l0_checks(mode, shot, ctx)
    for rule in triggered:
        found += [(rule, code) for code in L1_CHECKS[rule](shot, ctx)]
    for rid, cspec in custom.items():
        if rid in active and mode in ("shot", "nbp"):
            fired, cerrs = run_custom_rule(cspec, shot)
            if fired:
                triggered.append(rid)
                found += [(rid, code) for code in cerrs]
    if mode == "workflow_case" and not triggered and not found:
        found.append(("L0", "SCHEMA_EMPTY_OR_UNRECOGNIZED"))
    require_inj = bool(extra.get("require_l1_injection"))
    found += injection_errors(ctx.get("l1_injected"), bool(ctx.get("has_explicit_l1_injected")), require_inj, triggered)
    creative = ctx.get("creative_mode") or shot.get("creative_mode") or payload.get("creative_mode")
    craft_errors, warnings = craft_checks(shot, creative)
    found.extend(("craft", err) for err in craft_errors)
    errors = list(dict.fromkeys(code for _, code in found))
    constraints = []
    focus = []
    for rule in triggered:
        if rule in L1_RULES:
            constraints.append({"rule": rule, "constraints": L1_RULES[rule]["constraints"]})
            focus.append(L1_RULES[rule]["question"])
        elif rule in custom:
            constraints.append({"rule": rule, "constraints": custom[rule]["constraints"]})
            focus.append(custom[rule]["question"])
    return {
        "mode": mode,
        "verdict": "FAIL" if errors else "PASS",
        "triggered_l1_rules": triggered,
        "l0_rules": [rule["id"] for rule in L0_RULES],
        "blocking_errors": errors,
        "warnings": warnings,
        "error_rules": {code: rule for rule, code in found},
        "injected_constraints": constraints,
        "post_gen_focus": focus,
    }


# --------------------------------------------------------------------------- mistake book access


def load_book(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{number}: {exc.msg}") from exc
    return rows


def active_rules_from(book: Path | None) -> set[str] | None:
    """L1 rules still ACTIVE in the mistake book; None (all built-in rules) when the book is absent."""
    if book is None or not book.is_file():
        return None
    return active_rules_of(load_book(book))


def active_rules_of(rows: list[dict[str, Any]]) -> set[str]:
    """Every L1 rule except those whose book entries are DEPRECATED/CANDIDATE without an ACTIVE entry."""
    inactive = {row.get("rule_id") for row in rows if row.get("status") in ("DEPRECATED", "CANDIDATE")}
    active = {row.get("rule_id") for row in rows if row.get("status") == "ACTIVE"}
    custom = set(custom_rules_of(rows))
    return ((set(L1_RULES) - inactive) | (active & set(L1_RULES)) | custom)


def rubric_for(l1_rules: list[str], active_rules: set[str] | None = None,
               book_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Atomic binary Clean-Room rubric: L0 5 items + atomic items for each active triggered L1 rule."""
    keys = ("id", "question", "pass_example", "fail_example", "repair_route",
            "requires_audio", "requires_motion", "needs_anchor")
    items = [{key: rule[key] for key in keys} for rule in L0_RULES]
    custom = custom_rules_of(book_rows or [])
    for rule in dict.fromkeys(l1_rules):
        if active_rules is not None and rule not in active_rules:
            continue
        if rule in L1_RULES:
            for sub in L1_RULES[rule]["rubric_items"]:
                items.append({**{key: sub[key] for key in keys}, "parent_rule": rule})
        elif rule in custom and isinstance(custom[rule]["detector"].get("rubric"), dict):
            rub = custom[rule]["detector"]["rubric"]
            items.append({
                "id": rule, "parent_rule": rule,
                "question": rub["question"], "pass_example": rub["pass_example"],
                "fail_example": rub["fail_example"], "repair_route": rub["repair_route"],
                "requires_audio": bool(rub.get("requires_audio", False)),
                "requires_motion": bool(rub.get("requires_motion", False)),
                "needs_anchor": bool(rub.get("needs_anchor", False)),
            })
    return items
