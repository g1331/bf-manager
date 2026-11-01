"""Blaze 名单报文整理成接口用的结构"""

import time
from typing import Any

from loguru import logger


class BlazeData:
    language_dict = {
        "zh": "中",
        "ru": "俄",
        "en": "英",
        "th": "泰",
        "de": "德",
        "fr": "法",
        "it": "意",
        "pl": "波",
        "dk": "力",
        "cs": "捷",
        "hu": "匈",
        "ko": "韩",
        "es": "西",
        "ja": "日",
        "pt": "葡",
        "nl": "荷",
        "tr": "土",
        "sv": "瑞",
        "no": "挪",
        "fi": "芬",
        "ro": "罗",
        "ar": "阿",
    }

    @staticmethod
    def player_list_handle(data: dict[str, Any]) -> dict[int, Any] | str:
        """
        处理玩家列表数据
        origin:
        {
        "method": "GameManager.getGameDataFromId",
        "type": "Result",
        "id": 7,
        "length": 55126,
        "data": {
            "GDAT 43": []
        }
        :param data:
        :return:
        eg:
        {
            "8622724970463": {
            "server_name": "[JIAOYUAN#3]Noob welcome/NO SMG0818/qun642283064",
            "game_id": 8622724970463,
            "players": [
                {
                    "display_name": "Saber-master520",
                    "pid": 1004755893484,
                    "uid": 1009760693484,
                    "role": "spectator",
                    "rank": "28",
                    "latency": "27",
                    "team": 65535
                }
            ],
            "queues": 0,
            "spectator": 1,
            "max_player": 64
        }
        """
        result: dict[int, Any] = {}
        if not data["data"]:
            return result
        if data["type"] == "Error":
            error_code = data.get("data", {}).get("ERRC", "Known")
            return f"Blaze查询出错!错误代码:{error_code}"
        for server_data in data["data"]["GDAT"]:
            game_id = server_data["GID"]
            server_name = server_data["GNAM"]
            # queue = server_data["QCNT 0"]
            # spectator = server_data["PCNT 40"][2]
            server_attribute = server_data["ATTR"]
            operation_info = {}
            if server_attribute.get("operationindex"):
                operation_info["operationstate"] = server_attribute["operationstate"]
                operation_info["operationindex"] = server_attribute["operationindex"]
                operation_info["progress"] = server_attribute["progress"]

            max_player = server_data["CAP"][0]
            players = []
            queues = []
            spectators = []
            if "ROST" in server_data:
                for player in server_data["ROST"]:
                    role = player["ROLE"]
                    if role == "":
                        role = "spectator"
                    try:
                        rank = int(player["PATT"].get("rank", 0))
                    except KeyError:
                        logger.debug(player)
                        rank = 0
                    try:
                        latency = int(player["PATT"].get("latency", 0))
                    except KeyError:
                        logger.debug(player)
                        latency = 0
                    join_time = player["JGTS"] / 1000000 if player.get("JGTS") else None
                    display_name = player["NAME"]
                    pid = player["PID"]
                    uid = player["EXID"]
                    team = player["TIDX"]
                    language = player["LOC"].to_bytes(4, byteorder="big").decode("ascii")
                    language = BlazeData.language_dict.get(language[:2], language[:2])
                    # 排队者 ROLE 为 soldier、TIDX 65535，观战者 ROLE 为空。部分排队者（STAT 1）
                    # 已带等级，不能按「等级为 0」判断，否则会被当成未定队位、从名单里漏掉
                    if team == 65535 and role != "spectator":
                        role = "queue"
                    # STAT：0 预约 / 1 排队 / 2 载入中 / 4 在游戏。已占队伍或观战位、还没进到游戏的
                    # 算载入中（2026-10-31 实测通常 1–16 秒），这时 JGTS 可能为 0、延迟为 -1
                    loading = role != "queue" and player.get("STAT", 4) != 4
                    player_data = {
                        "display_name": display_name,
                        "pid": pid,
                        "uid": uid,
                        "role": role,
                        "rank": rank,
                        "latency": latency,
                        "team": team,
                        "join_time": join_time,
                        "platoon": {},
                        "language": language,
                        "loading": loading,
                    }
                    if role == "queue":
                        queues.append(player_data)
                    elif role == "spectator":
                        spectators.append(player_data)
                    else:
                        players.append(player_data)
            result[game_id] = {
                "server_name": server_name,
                "game_id": game_id,
                "players": players,
                "queues": queues,
                "spectators": spectators,
                "max_player": max_player,
                "time": time.time(),
                "operation_info": operation_info,
                "attributes": server_attribute,
            }
        return result
