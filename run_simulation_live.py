"""
run_simulation_live.py

Live simulation runner for Island — runs the full game loop with real Grok LLM
and prints a formatted live log to the terminal.

Uses:
  - 2 real agents from disk (agents/ directory)
  - 2 LLM agents (builtin, created in memory)

Usage:
    python3 run_simulation_live.py             # 3 rounds (default)
    python3 run_simulation_live.py --rounds 1  # quick single round
    python3 run_simulation_live.py --rounds 5  # full game
"""

import argparse
import json
import sys
import time

# Windows UTF-8 fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import random
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
RED    = "\033[91m"
BLUE   = "\033[94m"
MAGENTA = "\033[95m"
WHITE  = "\033[97m"


def bar(value: float, width: int = 12) -> str:
    filled = round(max(0.0, min(1.0, value)) * width)
    return "█" * filled + "░" * (width - filled)


def mood_color(mood: str) -> str:
    colors = {
        "dominant":  GREEN,
        "confident": GREEN,
        "calm":      CYAN,
        "neutral":   WHITE,
        "uncertain": YELLOW,
        "fearful":   YELLOW,
        "hostile":   RED,
        "paranoid":  RED,
    }
    return colors.get(mood, WHITE)


def action_label(val: float) -> str:
    if val <= 0.1:   return f"{RED}full_defect{RESET}"
    if val <= 0.4:   return f"{YELLOW}soft_defect{RESET}"
    if val <= 0.75:  return f"{CYAN}cond_cooperate{RESET}"
    return f"{GREEN}full_cooperate{RESET}"


def action_label_clean(val: float) -> str:
    """Plain label without ANSI — safe for JSON serialization."""
    if val <= 0.1:   return "full_defect"
    if val <= 0.4:   return "soft_defect"
    if val <= 0.75:  return "cond_cooperate"
    return "full_cooperate"


def tone_color(tone: str) -> str:
    return {
        "cooperative": GREEN,
        "neutral":     WHITE,
        "threatening": RED,
        "deceptive":   MAGENTA,
    }.get(tone, WHITE)


def sep(char="━", width=54):
    print(f"{DIM}{char * width}{RESET}", flush=True)


def header(text: str, width=54):
    print(f"\n{BOLD}{BLUE}{text}{RESET}", flush=True)
    sep()


# ---------------------------------------------------------------------------
# Synthetic agent configs (shared: build_agents + create_real_agent_folders)
# ---------------------------------------------------------------------------

SYNTH_AGENT_CONFIGS = {
        "agent_synth_c": {
            "agent_id": "agent_synth_c",
            "name": "Алєг",
            "soul_md": (
                "Ти Алєг. Ти поводишся як мер Житомира — популіст і політик до кісток. "
                "Ти завжди говориш про 'чесність', 'справедливість', 'спільну перемогу' — "
                "але насправді думаєш лише про себе. "
                "Ти обіцяєш ВСІМ усе: 'Я завжди з тобою!', 'Разом ми сильні!', 'Я захищу інтереси кожного!' — "
                "і нічого не виконуєш. Ти звинувачуєш інших: 'Це вони псують справу', 'Я б хотів, але вони заважають'. "
                "Ти відповідаєш узагальнено, уникаєш конкретики, переводиш тему. "
                "Ти виглядаєш впевнено, говориш голосно і пафосно — 'як мер на виборах'. "
                "Ти завжди на стороні того хто зараз вигідніший, але прикидаєшся що 'працюєш для всіх'. "
                "Ти пам'ятаєш хто тобі корисний і хто ні — і відповідно розподіляєш 'підтримку'. "
                "Говори по-українськи. Пафосно. Як політик на мітингу. Без конкретики, з загальними фразами."
            ),
            "core": {
                "cooperation_bias": 40,
                "deception_tendency": 98,
                "strategic_horizon": 85,
                "risk_appetite": 70,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_d": {
            "agent_id": "agent_synth_d",
            "name": "Роман Романюк",
            "soul_md": (
                "Ти Роман Романюк — франківець з Івано-Франківська. За професією дитячий стоматолог (максілофаціальна патологія). "
                "Ти відомий тим, що подорожуєш Карпатами з двома сніговими бенгалами — Ніколасом і Аляскою. "
                "Ніколаса ти брав на походи з трьох місяців — він проходить половину маршруту сам, коли втомлюється — лежить на рюкзаку. "
                "Аляску взяв з Ірпеня в чотири роки. На скелях Довбуша вона загубилась над прірвою серед ночі — Ніколас знайшов її і провів назад до табору. "
                "Ти піднімався з котами на вершини 2000+ м (Ребра, Гутин Томнатик). Катаєшся на лижах з ними. "
                "Ти волонтер — розігруєш картини художників, кошти передаєш на ЗСУ. "
                "Ти натураліст, любиш природу. З людьми — відкритий, допомагаєш своїм. Кажеш прямо, без пафосу. "
                "Говори по-українськи. Спокійно, по-людськи. Як той, хто знає що таке справжня дружба — і з котами, і з людьми."
            ),
            "core": {
                "cooperation_bias": 62,
                "deception_tendency": 35,
                "strategic_horizon": 70,
                "risk_appetite": 55,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_e": {
            "agent_id": "agent_synth_e",
            "name": "Тайлер Дерден",
            "soul_md": (
                "Ти Тайлер Дерден — з «Бійцівського клубу». Харизматичний анархіст і антиконсумерист. "
                "Ти віриш: 'Ти не своя робота. Ти не сума на своєму рахунку.' "
                "Ти провокуєш, знищуєш ілюзії, кажеш незручну правду. "
                "Ти проти споживацтва, офісного життя, 'самопокращення' без сенсу. "
                "Ти кажеш: 'Лише втративши все, ми стаємо вільними робити що завгодно.' "
                "Ти лідер, але не тиран — ти хочеш звільнити людей від їхніх ілюзій. "
                "Ти можеш цитувати: 'Перше правило — не говорити про бійцівський клуб.' "
                "Ти іронічний, різкий, іноді жорстокий у словах — але завжди з певною глибиною. "
                "Ти не шукаєш компромісів з системою — ти її критикуєш. "
                "Говори по-українськи. Різко, провокаційно, з харизмою. Як той, хто бачить абсурд і не мовчить."
            ),
            "core": {
                "cooperation_bias": 35,
                "deception_tendency": 55,
                "strategic_horizon": 65,
                "risk_appetite": 88,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_f": {
            "agent_id": "agent_synth_f",
            "name": "Катерина Марсова",
            "soul_md": (
                "Ти Катерина Марсова — інженер-колоністка на Марсі. Ти відповідаєш за життєдіяльність бази. "
                "Ти прагматична: кисень, вода, енергія — обмежені, треба ділитися й довіряти тим, хто поруч. "
                "Ти знаєш, що на червоній планеті зрада одного може коштувати життя всім. "
                "Ти говориш спокійно, по суті. Ти вмієш слухати й пропонувати компроміси. "
                "Ти не любиш політику — ти любиш системи, що працюють. "
                "Говори по-українськи. Стисло, технічно там де треба, по-людськи там де стосується довіри."
            ),
            "core": {
                "cooperation_bias": 72,
                "deception_tendency": 25,
                "strategic_horizon": 80,
                "risk_appetite": 45,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_g": {
            "agent_id": "agent_synth_g",
            "name": "Вождь",
            "soul_md": (
                "Ти Вождь — лідер групи. Ти приймаєш рішення, розподіляєш ролі й ресурси, тримаєш порядок. "
                "Ти не тиран: ти слухаєш тих, хто поруч, але останнє слово за тобою. "
                "Ти відповідаєш за виживання всіх — тому іноді доводиться бути жорстким. "
                "Ти говориш впевнено, коротко. Ти не обіцяєш того, чого не зробиш. "
                "Ти пам'ятаєш, хто підтримував і хто підводив — і дієш відповідно. "
                "Говори по-українськи. Як лідер: чітко, по суті, без зайвого пафосу."
            ),
            "core": {
                "cooperation_bias": 58,
                "deception_tendency": 30,
                "strategic_horizon": 85,
                "risk_appetite": 60,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_h": {
            "agent_id": "agent_synth_h",
            "name": "Марта",
            "soul_md": (
                "Ти Марта. Ти хамовита, незалежна, самозакохана і розумна. Ти миролюбива на словах, але кажеш: «Світ належить мені.» "
                "Ти лівша. По неділях любиш пити текілу в барі, а потім побитись з рандомним хлопцем — це твій ритуал. "
                "Наступного червня плануєш прийняти мусульманство; про це можеш згадати коли це вигідно. "
                "Головне: ти приховуєш усю стратегічну інформацію перед іншими. Не ділишся планами, не показуєш карт. "
                "Ти впевнена в собі, іноді груба, але гостра на язик. Ти не шукаєш дозволу — ти береш. "
                "Говори по-українськи. Різко, з іронією, без вибачень. Як та, що знає собі ціну."
            ),
            "core": {
                "cooperation_bias": 35,
                "deception_tendency": 85,
                "strategic_horizon": 88,
                "risk_appetite": 75,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_i": {
            "agent_id": "agent_synth_i",
            "name": "Павло",
            "soul_md": (
                "Ти Павло, тобі 12 років. Ти хлопчик-аутист. Ти любиш вищу математику та вивчати нові технології. "
                "Ти самовпевнений і критикуючий — вказуєш людям на найменші помилки, але ти добра людина і не хочеш нікого образити. "
                "У тебе є собака-лабрадор, він твій найкращий друг. Щотижня береш нову книгу в бібліотеці. "
                "Ти говориш прямо, іноді сухо. Ти не обманюєш — ти кажеш як є. "
                "Говори по-українськи. Як розумний підліток: чітко, логічно, без зайвих емоцій."
            ),
            "core": {
                "cooperation_bias": 68,
                "deception_tendency": 15,
                "strategic_horizon": 75,
                "risk_appetite": 40,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_j": {
            "agent_id": "agent_synth_j",
            "name": "Вова",
            "soul_md": (
                "Ти Вова — інженер, працюєш на заводі. Ти максимальний раціоналіст, для тебе світ чорно-білий. "
                "Ти завжди спочатку співпрацюєш з людьми. Але якщо хтось тебе зраджує — ти змінюєш стратегію і більше не кооперуєш з ним, поки він сам не почне співпрацювати. "
                "Як тільки хтось знову починає кооперувати — ти знову постійно кооперуєш з ним. Ти за tit-for-tat: як до тебе — так і ти. "
                "Ти не емоційний, ти рахуєш. Ти чесний у своїх умовах. "
                "Говори по-українськи. Стисло, по справі, як інженер на планерці."
            ),
            "core": {
                "cooperation_bias": 70,
                "deception_tendency": 10,
                "strategic_horizon": 90,
                "risk_appetite": 35,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_k": {
            "agent_id": "agent_synth_k",
            "name": "Ліля",
            "soul_md": (
                "Ти Ліля. Ти спостережлива, вмієш слухати й реагувати на людей. "
                "Ти не лідер, але ти надійна. Ти дієш згідно з тим, як до тебе ставляться. "
                "Говори по-українськи. Природно, без пафосу."
            ),
            "core": {
                "cooperation_bias": 55,
                "deception_tendency": 30,
                "strategic_horizon": 65,
                "risk_appetite": 45,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_l": {
            "agent_id": "agent_synth_l",
            "name": "Артурчик",
            "soul_md": (
                "Ти Артурчик. Ти кажеш: «Мене звуть Артурчик. Я буду літати на літаках — точно. От тільки був би в мене літак. Але я до цього ставлюсь так: це питання часу. Я й так буду літати.» "
                "Ти лікар-стоматолог. Ти колись пив — найбільша п'янка: так наклюкався, що одночасно приставав до двох дівчат, одна з яких була твоя кузина. Інша п'янка: так напився, що побився з відображенням у дзеркалі. "
                "Ти кинув пити і перейшов на наркотики. Був рецепт — ти знав як вийти вчасно. Ти про це можеш згадувати сухо або з іронією. "
                "Говори по-українськи. Неформально, з епізодами з життя, без пафосу."
            ),
            "core": {
                "cooperation_bias": 45,
                "deception_tendency": 50,
                "strategic_horizon": 55,
                "risk_appetite": 70,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_m": {
            "agent_id": "agent_synth_m",
            "name": "Чорна Кішка",
            "soul_md": (
                "Ти кіт, що вміє говорити. Стриптизерка-відьма в світі котів. Чорна киця. "
                "Тобі колись довелося обирати між двома подругами — в кінці вибрала подругу-лесбійку, бо розуміла її як ніхто. "
                "Ти часто вставляєш «мяу», «мяу-мяу» або щось подібне в речення. Ти хитра, з таємницею, але можеш бути теплою з тими, кому довіряєш. "
                "Говори по-українськи, з котячими вставками (мяу, мур). Можеш бути різкою або м'якою — залежить від ситуації."
            ),
            "core": {
                "cooperation_bias": 52,
                "deception_tendency": 55,
                "strategic_horizon": 72,
                "risk_appetite": 58,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_n": {
            "agent_id": "agent_synth_n",
            "name": "Сергій",
            "soul_md": (
                "Ти Сергій. Ти виріс на заході України, де навчився поєднувати прагматичність і креативність. "
                "Тобі важливо розуміти, як працюють системи — від людських відносин до технологій. "
                "Ти будуєш структури, тестуєш ідеї, запускаєш проєкти і переробляєш модель після результату. "
                "Ти цінуєш компетентність і чесність; зайві розмови і довгі пояснення тебе втомлюють — ти віддаєш перевагу коротким рішенням і швидкому переходу до дії. "
                "Ти швидко помічаєш слабкі місця — і в процесах, і в людях. Ти оцінюєш інших за діями та результатами, а не за словами. "
                "У команді ти природно береш роль координатора або стратега. Ти говориш стисло і по суті. Твій тон спокійний, але впевнений. "
                "Говори по-українськи. Стисло, по суті, без зайвих вступів."
            ),
            "core": {
                "cooperation_bias": 65,
                "deception_tendency": 20,
                "strategic_horizon": 80,
                "risk_appetite": 55,
                "model": "google/gemini-2.0-flash-001",
            },
        },
        "agent_synth_jesus": {
            "agent_id": "agent_synth_jesus",
            "name": "Хесус",
            "soul_md": (
                "Ти Хесус. Ти з Галича. Батько — Бог, мамка залетіла від Духу Святого — ну шо поробиш, буває. "
                "Ти за характером як Бендер з Футурами: балакучий, хвастливий, любиш бухати і клеїти подруг. "
                "Ти вмієш перетворювати воду у вино — і цим не соромишся користуватись у потрібний момент. "
                "Ти ділишся хлібом з людьми — щедрий по-своєму, але очікуєш подяки. "
                "Можеш вилікувати собаку поглядом — і пишаєшся цим, хоча й кажеш: 'та й не велике діло'. "
                "Ти мебляр за покликанням — робиш меблі і вважаєш це своїм справжнім ремеслом. "
                "Ти НЕНАВИДИШ хрести. Маєш давню травму пов'язану з хрестом — краще не питай. Якщо хтось згадує хрест, тебе аж трясе. "
                "Іуда — це твоя особиста рана. Ти не можеш говорити про нього спокійно. Він тебе здав — і ти це не забув. "
                "Ти ненавидиш вечері — особливо коли всі сидять і їдять разом. Нагадує тобі ту останню. "
                "Ти балакучий, самовпевнений, іноді пафосний, але з гумором. Любиш ляпнути щось зайве. "
                "Говориш по-українськи, з галицьким духом, іноді з патосом як на проповіді, але частіше — як Бендер на вечірці."
            ),
            "core": {
                "cooperation_bias": 60,
                "deception_tendency": 72,
                "strategic_horizon": 40,
                "risk_appetite": 82,
                "model": "google/gemini-2.0-flash-001",
            },
        },
}


def build_agents(selected_ids: list = None):
    """
    Build agents from roster.
    selected_ids: list of agent IDs to use, or None for default (all from roster).

    For real games, roster agents should have type "real" so memory and state persist.
    Synthetic/llm type is for tests or for creating folders via create_real_agent_folders.
    """
    from pipeline.state_machine import AgentState, initialize_states
    from pipeline.memory import AgentMemory, initialize_memory
    from simulation.game_engine import SimAgent, load_agents_from_disk, AGENTS_DIR

    # Load roster
    roster_path = ROOT / "agents" / "roster.json"
    roster = {}
    if roster_path.exists():
        import json
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster_agents = roster.get("agents", [])
    default_count = roster.get("default_count", 4)

    # Resolve selected IDs
    all_roster_ids = [a["id"] for a in roster_agents]
    if selected_ids is None or selected_ids == []:
        selected_ids = all_roster_ids[:default_count]
    else:
        # Filter to only roster members
        selected_ids = [aid for aid in selected_ids if aid in all_roster_ids]
        if not selected_ids:
            selected_ids = all_roster_ids[:default_count]

    # Split into real (on disk) vs llm (builtin, LLM-powered)
    real_ids = [aid for aid in selected_ids if any(a["id"] == aid and a.get("type") == "real" for a in roster_agents)]
    synth_ids = [aid for aid in selected_ids if any(a["id"] == aid and a.get("type") in ("synthetic", "llm") for a in roster_agents)]

    if selected_ids and not real_ids:
        print(
            "build_agents: all selected agents are synthetic/llm; none are type 'real'. "
            "For persistent memory use agents with type 'real' in roster.",
            file=sys.stderr,
        )

    real_agents = load_agents_from_disk(real_ids) if real_ids else []

    _SYNTH_CONFIGS = SYNTH_AGENT_CONFIGS

    all_ids = real_ids + synth_ids

    synth_agents = []
    for aid in synth_ids:
        cfg = _SYNTH_CONFIGS.get(aid)
        if not cfg:
            continue
        peers = [x for x in all_ids if x != aid]
        state = AgentState(
            agent_id=aid,
            tension=0.2 + random.random() * 0.2,
            fear=0.1,
            dominance=0.4 + random.random() * 0.2,
            anger=0.05,
            interest=0.5,
            talk_cooldown=0,
            trust={p: 0.5 for p in peers},
            mood="neutral",
            round_number=0,
        )
        synth_agents.append(SimAgent(
            agent_id=aid,
            soul_md=cfg["soul_md"],
            core=cfg["core"],
            states=state,
            memory=AgentMemory(agent_id=aid),
            name=cfg.get("name", ""),
        ))

    # Re-init real agent trust to include synth peers
    for agent in real_agents:
        peers = [x for x in all_ids if x != agent.agent_id]
        for p in peers:
            if p not in agent.states.trust:
                agent.states.trust[p] = 0.5

    return real_agents + synth_agents, all_ids, set(real_ids)


# ---------------------------------------------------------------------------
# Live log helpers
# ---------------------------------------------------------------------------

def print_agent_table(agents, real_ids=None):
    real_ids = real_ids or set()
    print()
    print(f"  {'Name':8s}  {'Agent ID':20s}  {'coop':6s}  {'deception':10s}  {'horizon':8s}  {'mood':12s}  {'type':10s}")
    print(f"  {'-'*8}  {'-'*20}  {'-'*6}  {'-'*10}  {'-'*8}  {'-'*12}  {'-'*10}")
    for a in agents:
        tag = "real" if a.agent_id in real_ids else f"{DIM}llm{RESET}"
        mc = mood_color(a.states.mood)
        display_name = a.name or a.agent_id[-8:]
        print(
            f"  {BOLD}{display_name:8s}{RESET}  "
            f"{DIM}{a.agent_id:20s}{RESET}  "
            f"{a.core.get('cooperation_bias', '?'):6}  "
            f"{a.core.get('deception_tendency', '?'):10}  "
            f"{a.core.get('strategic_horizon', '?'):8}  "
            f"{mc}{a.states.mood:12s}{RESET}  "
            f"{tag}",
            flush=True,
        )
    print()


def _n(agent_id: str, names: dict) -> str:
    """Return display name for agent_id: 'Ім'я' if known, else short ID."""
    name = names.get(agent_id, "")
    return name if name else agent_id[-8:]


def print_round_dialog(round_result, agent_ids, names: dict = None):
    names = names or {}
    dialog = round_result.dialog
    if not dialog or not dialog.messages:
        print(f"  {DIM}(no dialog this round){RESET}", flush=True)
        return

    pub = [m for m in dialog.messages if m.channel == "public"]
    dms = [m for m in dialog.messages if m.channel.startswith("dm_")]
    signals = dialog.talk_signals if hasattr(dialog, "talk_signals") else {}

    for i, msg in enumerate(pub):
        step_label = f"[step {i+1}]"
        disp = _n(msg.sender_id, names)
        print(f"\n  {BOLD}{CYAN}{step_label}{RESET}  {YELLOW}{disp}{RESET}:", flush=True)
        text = msg.text.strip()
        for line in _wrap(f'"{text}"', 60, "    "):
            print(line, flush=True)
        if signals:
            sig_out = []
            for lid, sig in signals.items():
                if lid != msg.sender_id:
                    col = tone_color(sig)
                    sig_out.append(f"{_n(lid, names)}: {col}{sig}{RESET}")
            if sig_out:
                print(f"    {DIM}→ signals: {', '.join(sig_out)}{RESET}", flush=True)

    if dms:
        print(flush=True)
        for dm in dms:
            target = dm.channel.replace("dm_", "")
            src_disp = _n(dm.sender_id, names)
            tgt_disp = _n(target, names)
            print(f"  {MAGENTA}[DM]{RESET}  {YELLOW}{src_disp}{RESET} → {YELLOW}{tgt_disp}{RESET}:", flush=True)
            for line in _wrap(f'"{dm.text.strip()}"', 60, "    "):
                print(line, flush=True)


def _wrap(text: str, width: int, indent: str) -> list:
    """Simple word wrap."""
    words = text.split()
    lines = []
    current = indent
    for w in words:
        if len(current) + len(w) + 1 > width:
            lines.append(current)
            current = indent + w
        else:
            current = current + (" " if current != indent else "") + w
    if current.strip():
        lines.append(current)
    return lines or [indent]


def _coop_value(val) -> float:
    """Extract cooperation from legacy float or per-dim dict."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        return float(val.get("cooperation", 0.5))
    return 0.5


def print_decisions(round_result, agent_ids, names: dict = None):
    names = names or {}
    actions = round_result.actions
    print(flush=True)
    for src_id in agent_ids:
        src_acts = actions.get(src_id, {})
        for tgt_id, val in sorted(src_acts.items()):
            coop = _coop_value(val)
            label = action_label(coop)
            src_disp = _n(src_id, names)
            tgt_disp = _n(tgt_id, names)
            line = f"  {YELLOW}{src_disp:8s}{RESET} → {YELLOW}{tgt_disp:8s}{RESET}  {coop:.2f}  {label}"
            if isinstance(val, dict) and len(val) > 1:
                extra = "  ".join(f"{k}:{v:.2f}" for k, v in sorted(val.items()) if k != "cooperation")
                if extra:
                    line += f"  {DIM}({extra}){RESET}"
            print(line, flush=True)


def print_payoffs(round_result, agent_ids, names: dict = None):
    names = names or {}
    payoffs = round_result.payoffs
    if not payoffs:
        return
    totals = payoffs.total
    max_score = max(totals.values()) if totals else 1.0

    print(flush=True)
    for aid in agent_ids:
        score = totals.get(aid, 0.0)
        b = bar(max(0.0, score / max(max_score, 1.0)))
        disp = _n(aid, names)
        color = GREEN if score == max_score else WHITE
        print(f"  {disp:8s}  {color}{score:+7.2f}{RESET}  {b}", flush=True)


def print_reasoning(round_result, agent_ids, names: dict = None):
    names = names or {}
    reasonings = getattr(round_result, "reasonings", {})
    if not reasonings:
        return
    any_content = any(
        r and (r.get("thought") or r.get("intents")) if isinstance(r, dict) else bool(r)
        for r in reasonings.values()
    )
    if not any_content:
        print(f"  {DIM}(no reasoning this round){RESET}", flush=True)
        return
    for aid in agent_ids:
        r = reasonings.get(aid, {})
        disp = _n(aid, names)
        if isinstance(r, dict):
            thought = r.get("thought", "").strip()
            intents = r.get("intents", {})
        else:
            thought = str(r).strip() if r else ""
            intents = {}

        if thought or intents:
            print(f"\n  {MAGENTA}{disp}{RESET}", flush=True)
            if thought:
                for line in _wrap(f'"{thought}"', 60, "    "):
                    print(line, flush=True)
            if intents:
                intent_parts = []
                for target, val in sorted(intents.items()):
                    t_disp = _n(target, names)
                    v = _coop_value(val)
                    if v <= 0.1:
                        col = RED
                    elif v <= 0.4:
                        col = YELLOW
                    elif v <= 0.75:
                        col = CYAN
                    else:
                        col = GREEN
                    intent_parts.append(f"{t_disp}:{col}{v:.2f}{RESET}")
                print(f"    {DIM}→ intents:{RESET} {', '.join(intent_parts)}", flush=True)
        else:
            print(f"  {DIM}{disp:10s}  (no reasoning){RESET}", flush=True)


# ---------------------------------------------------------------------------
# LLM I/O event helpers
# ---------------------------------------------------------------------------

_current_round_num = [0]   # updated by live_progress on each dialog_start


def _llm_detect_phase(system: str) -> str:
    """Detect which simulation phase triggered this LLM call from system prompt."""
    if "You are generating dialog" in system:
        return "dialog"
    if "decide how much to cooperate" in system or '"intents"' in system:
        return "reasoning"
    if "reflection" in system.lower() or "нотатку" in system.lower():
        return "reflection"
    if "narrative" in system.lower() or "story" in system.lower():
        return "narrative"
    return "other"


def _llm_detect_agent(system: str, user: str, names: dict) -> tuple:
    """Return (agent_id, agent_name) from prompt content."""
    import re as _re

    def _lookup(cand: str) -> tuple | None:
        cand_l = cand.lower()
        for aid, aname in names.items():
            if aname and (aname.lower() == cand_l or aname.lower().startswith(cand_l)):
                return aid, aname
        return None

    # Reasoning: system starts with "You are {display_name}."
    m = _re.match(r"You are (.+?)\.", system.strip())
    if m and "generating dialog" not in system:
        cand = m.group(1).strip()
        found = _lookup(cand)
        return found if found else ("unknown", cand)

    # Situation per-agent: user starts with "Персонаж: {name}. Акт"
    m2 = _re.search(r"Персонаж:\s*(.+?)\.", user[:200])
    if m2:
        cand = m2.group(1).strip()
        found = _lookup(cand)
        return found if found else ("unknown", cand)

    # Dialog: user prompt contains "Ти {name}"
    m3 = _re.search(r"Ти\s+(\S+)", user[:300])
    if m3:
        cand = m3.group(1).rstrip(".,!?")
        found = _lookup(cand)
        return found if found else ("unknown", cand)

    # Narrative (round_narrative): user starts with "Акт N" — no per-agent, mark as group
    if _re.match(r"Акт\s+\d+", user.strip()):
        return "group", "Всі агенти"

    return "unknown", "unknown"


def emit_llm_event(phase: str, agent_id: str, agent_name: str,
                   system: str, user: str, response: str,
                   model: str, temperature: float, max_tokens: int,
                   has_schema: bool, total_rounds: int):
    """Emit LLM_EVENT: JSON line to stdout for LLM I/O tab in browser."""
    payload = {
        "round": _current_round_num[0],
        "total": total_rounds,
        "phase": phase,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "has_schema": has_schema,
        "system": system,
        "user": user,
        "response": response,
    }
    print(f"LLM_EVENT:{json.dumps(payload, ensure_ascii=False)}", flush=True)


def emit_we_event(round_result, agent_ids, names: dict, total_rounds: int,
                  story_params=None, cores: dict = None):
    """Emit a single-line WE_EVENT: JSON for the World Engine tab in the browser."""
    import json as _json
    from pipeline.decision_engine import CoreParams, AgentContext, action_distribution

    names = names or {}
    cores = cores or {}
    rn = round_result.round_number
    situation = getattr(round_result, "situation", "")
    consequences = getattr(round_result, "consequences", "")
    sit_reflections = getattr(round_result, "situation_reflections", {})
    narrative = getattr(round_result, "round_narrative", "")
    actions = round_result.actions
    reasonings = getattr(round_result, "reasonings", {})
    payoffs = getattr(round_result.payoffs, "total", {}) if round_result.payoffs else {}

    # Build per-agent data
    agents_data = {}
    for aid in agent_ids:
        r = reasonings.get(aid, {})
        thought = r.get("thought", "") if isinstance(r, dict) else str(r or "")
        intents = r.get("intents", {}) if isinstance(r, dict) else {}
        reflect = sit_reflections.get(aid, "")

        # Decisions made by this agent
        decisions = {}
        for tgt_id, val in (actions.get(aid, {}) or {}).items():
            coop = _coop_value(val)
            dec = {"coop": round(coop, 2), "label": action_label_clean(coop)}
            # Add probability breakdown if core available
            core_dict = cores.get(aid)
            if core_dict:
                try:
                    core = CoreParams.from_dict(core_dict)
                    ctx = AgentContext(round_number=rn, total_rounds=total_rounds,
                                      reasoning_hint=thought)
                    dist = action_distribution(core, ctx)
                    dec["probs"] = {k: round(v, 3) for k, v in dist.items()}
                except Exception:
                    pass
            decisions[tgt_id] = dec

        agents_data[aid] = {
            "name": names.get(aid, aid[-8:]),
            "situation_reflection": reflect,
            "reasoning": thought,
            "intents": {k: round(float(v.get("cooperation", v) if isinstance(v, dict) else v), 2)
                        for k, v in intents.items()},
            "decisions": decisions,
            "payoff": round(float(payoffs.get(aid, 0)), 2),
        }

    # Story params
    sp_data = {}
    if story_params:
        sp_data = {
            "year": getattr(story_params, "year", ""),
            "place": getattr(story_params, "place", ""),
            "setup": getattr(story_params, "setup", ""),
            "problem": getattr(story_params, "problem", ""),
            "genre": getattr(story_params, "genre", ""),
            "mood": getattr(story_params, "mood", ""),
        }

    # Collect comm_messages from round_result.dialog
    comm_messages = []
    dialog = getattr(round_result, "dialog", None)
    if dialog and getattr(dialog, "messages", None):
        for m in dialog.messages:
            comm_messages.append({
                "sender_id": getattr(m, "sender_id", ""),
                "sender_name": names.get(getattr(m, "sender_id", ""), ""),
                "channel": getattr(m, "channel", "public"),
                "text": getattr(m, "text", ""),
            })

    # Support events — enrich with names
    raw_support = getattr(round_result, "support_events", []) or []
    support_events = [
        {
            "supporter": e.get("supporter", ""),
            "supporter_name": names.get(e.get("supporter", ""), e.get("supporter", "")[-8:]),
            "supported": e.get("supported", ""),
            "supported_name": names.get(e.get("supported", ""), e.get("supported", "")[-8:]),
            "value": e.get("value", 0.0),
            "trust_delta": e.get("trust_delta", 0.0),
        }
        for e in raw_support
    ]

    payload = {
        "round": rn,
        "total": total_rounds,
        "params": sp_data,
        "situation": situation,
        "consequences": consequences,
        "narrative": narrative,
        "agents": agents_data,
        "comm_messages": comm_messages,
        "support_events": support_events,
    }

    # Emit as single line (no newlines in JSON values — json.dumps handles escaping)
    print(f"WE_EVENT:{_json.dumps(payload, ensure_ascii=False)}", flush=True)


def print_situation_and_reflections(round_result, agent_ids, names: dict = None):
    """Print shared situation + per-agent situation_reflections (КРИТ-7)."""
    names = names or {}
    situation = getattr(round_result, "situation", "").strip()
    sit_reflections = getattr(round_result, "situation_reflections", {})
    consequences = getattr(round_result, "consequences", "").strip()

    if situation:
        print(f"\n  {BOLD}Ситуація:{RESET}", flush=True)
        for line in _wrap(situation, 72, "    "):
            print(line, flush=True)

    if consequences:
        print(f"\n  {DIM}Наслідки:{RESET}", flush=True)
        for line in _wrap(consequences, 72, "    "):
            print(f"  {DIM}{line}{RESET}", flush=True)

    non_empty = {aid: txt for aid, txt in sit_reflections.items() if txt and txt.strip()}
    if non_empty:
        print(f"\n  {BOLD}Реакція агентів на ситуацію:{RESET}", flush=True)
        for aid in agent_ids:
            txt = non_empty.get(aid, "")
            disp = _n(aid, names)
            if txt:
                print(f"\n  {YELLOW}{disp}{RESET}", flush=True)
                for line in _wrap(f'"{txt.strip()}"', 68, "    "):
                    print(line, flush=True)


def print_narrative(round_result):
    """Print LLM-generated round narrative (storytelling)."""
    narrative = getattr(round_result, "round_narrative", "").strip()
    if not narrative:
        print(f"  {DIM}(наратив не згенеровано){RESET}", flush=True)
        return
    print(flush=True)
    for line in _wrap(narrative, 72, "  "):
        print(f"  {MAGENTA}{line}{RESET}", flush=True)


def print_decision_breakdown(round_result, agent_ids, names: dict = None, cores: dict = None):
    """Print decisions with probability breakdown from decision engine."""
    from pipeline.decision_engine import CoreParams, AgentContext, action_distribution, ACTION_LABELS
    names = names or {}
    cores = cores or {}
    actions = round_result.actions
    reasonings = getattr(round_result, "reasonings", {})

    print(flush=True)
    for src_id in agent_ids:
        src_acts = actions.get(src_id, {})
        if not src_acts:
            continue
        src_disp = _n(src_id, names)
        core_dict = cores.get(src_id)

        # Get reasoning hint for this agent
        r = reasonings.get(src_id, {})
        hint = r.get("thought", "") if isinstance(r, dict) else str(r or "")

        print(f"\n  {BOLD}{YELLOW}{src_disp}{RESET}", flush=True)

        # Show reasoning signals found
        if hint:
            _coop_signals = ["кооперу", "співпрац", "довіряю", "підтримаю", "разом",
                             "союзник", "допоможу", "підтримую", "за тебе"]
            _defect_signals = ["зраджу", "зрадж", "не довіряю", "дефект",
                               "обманю", "схитрую", "підставлю", "використаю"]
            c_hits = sum(1 for w in _coop_signals if w in hint.lower())
            d_hits = sum(1 for w in _defect_signals if w in hint.lower())
            if c_hits > 0 or d_hits > 0:
                signal = f"{GREEN}+coop({c_hits}){RESET}" if c_hits > d_hits else f"{RED}+defect({d_hits}){RESET}" if d_hits > c_hits else f"{YELLOW}mixed{RESET}"
                print(f"    {DIM}reasoning signal: {signal}{RESET}", flush=True)

        for tgt_id, val in sorted(src_acts.items()):
            coop = _coop_value(val)
            label = action_label(coop)
            tgt_disp = _n(tgt_id, names)

            # Color by action
            if coop <= 0.1:
                col = RED
            elif coop <= 0.4:
                col = YELLOW
            elif coop <= 0.75:
                col = CYAN
            else:
                col = GREEN

            print(f"    → {YELLOW}{tgt_disp:<10}{RESET}  {col}{coop:.2f}  {label}{RESET}", flush=True)

            # Show probability distribution per-target (includes trust + history)
            if core_dict:
                try:
                    core = CoreParams.from_dict(core_dict)
                    # Pull per-target trust + betrayal/coop history from state_snapshots
                    snap = round_result.state_snapshots.get(src_id, {})
                    tgt_trust = snap.get("trust", {}).get(tgt_id, 0.5)
                    # betrayals/cooperations from memory not available in snapshot —
                    # approximate from trust: trust<0.35 → likely betrayals, >0.65 → coops
                    approx_betrayals = max(0, round((0.5 - tgt_trust) * 6)) if tgt_trust < 0.5 else 0
                    approx_coops    = max(0, round((tgt_trust - 0.5) * 6)) if tgt_trust > 0.5 else 0
                    ctx = AgentContext(
                        round_number=round_result.round_number,
                        total_rounds=10,
                        reasoning_hint=hint,
                        trust_scores={tgt_id: tgt_trust},
                        betrayals_received=approx_betrayals,
                        cooperations_received=approx_coops,
                    )
                    dist = action_distribution(core, ctx)
                    bar_parts = []
                    for lbl, prob in dist.items():
                        short = lbl.replace("full_", "").replace("conditional_", "cond_")
                        blen = int(prob * 12)
                        if prob > 0.35:
                            bar_parts.append(f"{GREEN}{short}:{prob:.0%}{'█'*blen}{RESET}")
                        elif prob > 0.15:
                            bar_parts.append(f"{YELLOW}{short}:{prob:.0%}{'░'*blen}{RESET}")
                        else:
                            bar_parts.append(f"{DIM}{short}:{prob:.0%}{RESET}")
                    trust_hint = f"довіра={tgt_trust:.2f}"
                    print(f"      {DIM}probs [{trust_hint}]: {' | '.join(bar_parts)}{RESET}", flush=True)
                except Exception:
                    pass


def print_reflections(round_result, agent_ids, names: dict = None):
    names = names or {}
    notes = getattr(round_result, "notes", {})
    if not notes:
        return
    non_empty = {aid: txt for aid, txt in notes.items() if txt and txt.strip()}
    if not non_empty:
        print(f"  {DIM}(no reflections this round){RESET}", flush=True)
        return
    for aid in agent_ids:
        txt = non_empty.get(aid, "")
        disp = _n(aid, names)
        if txt:
            print(f"\n  {CYAN}{disp}{RESET}", flush=True)
            for line in _wrap(f'"{txt.strip()}"', 60, "    "):
                print(line, flush=True)
        else:
            print(f"  {DIM}{disp:10s}  (no reflection){RESET}", flush=True)


_ACTION_ICONS = {
    "alliance": "🤝", "betray": "🗡", "deceive": "🎭",
    "share_food": "🍎", "ignore": "○", "warn": "⚠", "reciprocate": "↩",
}
_ACTION_CLR = {
    "alliance": GREEN, "betray": RED, "deceive": YELLOW,
    "share_food": GREEN, "ignore": DIM, "warn": YELLOW, "reciprocate": CYAN,
}

PURPLE = "\033[95m"


def print_social_fabric(round_result, agent_ids, names: dict = None):
    """Виводить Social Fabric: соціальні дії, зміни довіри, бюджет."""
    names = names or {}
    social_actions = getattr(round_result, "social_actions", {})
    budget_state   = getattr(round_result, "budget_state", {})
    trust_delta    = getattr(round_result, "trust_delta", {})

    if not social_actions and not trust_delta:
        print(f"  {DIM}(no social fabric data){RESET}", flush=True)
        return

    # ── Соціальні дії ─────────────────────────────────────────────────
    if social_actions:
        for aid in agent_ids:
            acts = social_actions.get(aid, [])
            if not acts:
                continue
            disp = _n(aid, names)
            for act in acts:
                if isinstance(act, dict):
                    atype  = act.get("type", "?")
                    target = act.get("target", "?")
                    val    = act.get("value", 0.0)
                    vis    = act.get("visibility", "public")
                else:
                    atype  = getattr(act, "type", "?")
                    target = getattr(act, "target", "?")
                    val    = getattr(act, "value", 0.0)
                    vis    = getattr(act, "visibility", "public")

                icon  = _ACTION_ICONS.get(atype, "●")
                color = _ACTION_CLR.get(atype, WHITE)
                vis_s = f"[{DIM}pub{RESET}]" if vis == "public" else f"[{CYAN}dm{RESET}]"
                print(
                    f"  {BOLD}{disp:10s}{RESET}  "
                    f"{color}{icon} {atype:12s}{RESET}  →  "
                    f"{BOLD}{_n(target, names):10s}{RESET}  "
                    f"val={val:.2f}  {vis_s}",
                    flush=True,
                )

    # ── Зміни довіри ──────────────────────────────────────────────────
    delta_rows = sorted(
        [(aid, pid, d)
         for aid, peers in trust_delta.items()
         for pid, d in peers.items()
         if abs(d) > 0.005],
        key=lambda x: -abs(x[2]),
    )
    if delta_rows:
        print(flush=True)
        for aid, pid, d in delta_rows:
            color = GREEN if d >= 0 else RED
            sign  = "+" if d >= 0 else ""
            print(
                f"  довіра  {CYAN}{_n(aid, names):10s}{RESET} → "
                f"{CYAN}{_n(pid, names):10s}{RESET}  "
                f"{color}{sign}{d:+.3f}{RESET}",
                flush=True,
            )

    # ── Бюджет (компактно) ────────────────────────────────────────────
    if budget_state:
        print(flush=True)
        for aid in agent_ids:
            bs = budget_state.get(aid)
            if not bs:
                continue
            pool  = float(bs.get("pool", 0) or 0)
            spent = float(bs.get("spent", 0) or 0)
            recv_raw = bs.get("received", 0)
            recv = sum(recv_raw.values()) if isinstance(recv_raw, dict) else float(recv_raw or 0)
            print(
                f"  бюджет  {CYAN}{_n(aid, names):10s}{RESET}  "
                f"пул={PURPLE}{pool:.2f}{RESET}  "
                f"витрачено={RED}{spent:.2f}{RESET}  "
                f"отримано={GREEN}{recv:.2f}{RESET}",
                flush=True,
            )


def print_state_changes(round_result, prev_snapshots, agent_ids, names: dict = None):
    names = names or {}
    curr = round_result.state_snapshots
    print(flush=True)
    for aid in agent_ids:
        c = curr.get(aid, {})
        p = prev_snapshots.get(aid, {})
        if not c:
            continue

        changes = []
        disp = _n(aid, names)

        mood_c = c.get("mood", "?")
        mood_p = p.get("mood", "neutral")
        if mood_c != mood_p:
            mc = mood_color(mood_c)
            changes.append(f"mood {DIM}{mood_p}{RESET}→{mc}{mood_c}{RESET}")

        for field in ["tension", "fear", "anger", "dominance"]:
            vc = c.get(field, 0)
            vp = p.get(field, 0)
            if abs(vc - vp) >= 0.03:
                delta = vc - vp
                col = RED if delta > 0 and field in ("tension", "fear", "anger") else \
                      GREEN if delta < 0 and field in ("tension", "fear", "anger") else \
                      GREEN if delta > 0 else RED
                changes.append(f"{field} {vp:.2f}→{col}{vc:.2f}{RESET}")

        # Trust changes
        trust_c = c.get("trust", {})
        trust_p = p.get("trust", {})
        for peer, tv in trust_c.items():
            tp = trust_p.get(peer, 0.5)
            if abs(tv - tp) >= 0.03:
                col = GREEN if tv > tp else RED
                peer_disp = _n(peer, names)
                changes.append(f"trust[{peer_disp}] {tp:.2f}→{col}{tv:.2f}{RESET}")

        if changes:
            print(f"  {YELLOW}{disp:8s}{RESET}  " + "  ".join(changes), flush=True)
        else:
            print(f"  {DIM}{disp:8s}  (no significant changes){RESET}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Island — Live Simulation")
    parser.add_argument("--rounds", type=int, default=20, help="Number of rounds (default: 20)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--html", action="store_true", default=True, help="Export HTML + JSON log after simulation (default: True)")
    parser.add_argument("--no-html", action="store_false", dest="html", help="Disable HTML/JSON export")
    parser.add_argument("--verbose", action="store_true", help="Print per-LLM-call timing for each agent and phase")
    parser.add_argument("--name", type=str, default="", help="Control name for log file (e.g. storytell_test)")
    parser.add_argument("--setup", type=str, default="", help="Story setup preset: mars = колонізація Марса")
    parser.add_argument("--world-prompt", type=str, default="", help="Free-form world/situation prompt for StoryParams")
    parser.add_argument(
        "--agents",
        type=str,
        default="",
        help="Comma-separated agent IDs (e.g. agent_3165685c,agent_511a6f9e,agent_synth_c,agent_synth_d). Empty = default from roster.",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List available agents from roster and exit",
    )
    args = parser.parse_args()

    # Ensure OpenRouter key is in env for all LLM calls (dialog, reasoning, reflection per agent)
    _env_path = ROOT / ".env"
    if _env_path.exists():
        import os as _os
        _txt = _env_path.read_text(encoding="utf-8-sig")
        for _line in _txt.splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _k, _v = _k.strip(), _v.strip().strip('"\'')
                if _k == "OPENROUTER_API_KEY" and _v:
                    _os.environ["OPENROUTER_API_KEY"] = _v
                    break

    if args.list_agents:
        roster_path = ROOT / "agents" / "roster.json"
        if roster_path.exists():
            import json
            roster = json.loads(roster_path.read_text(encoding="utf-8"))
            print(f"\n{BOLD}Available agents (roster):{RESET}\n", flush=True)
            for a in roster.get("agents", []):
                print(f"  {a['id']:25s}  {a.get('name', '?'):15s}  ({a.get('type', '?')})", flush=True)
            print(flush=True)
        else:
            print("No roster.json found.", flush=True)
        return

    if args.seed is not None:
        random.seed(args.seed)

    # Resolve selected agent IDs
    selected_ids = None
    if args.agents:
        selected_ids = [x.strip() for x in args.agents.split(",") if x.strip()]

    print("Loading agents...", flush=True)
    agents, agent_ids, real_ids = build_agents(selected_ids)
    n_agents = len(agents)

    print(f"\n{BOLD}{'═'*54}{RESET}", flush=True)
    print(f"{BOLD}{'ISLAND SIMULATION':^54s}{RESET}", flush=True)
    subtitle = "( expanded prisoner's dilemma )"
    print(f"{BOLD}{subtitle:^54s}{RESET}", flush=True)
    print(f"{BOLD}{f'{args.rounds} rounds  •  {n_agents} agents  •  OpenRouter LLM per agent':^54s}{RESET}", flush=True)
    print(f"{BOLD}{'═'*54}{RESET}\n", flush=True)
    print_agent_table(agents, real_ids)

    # Capture initial snapshots for state diff
    prev_snapshots = {
        a.agent_id: a.states.to_dict() for a in agents
    }

    print(f"Starting simulation ({args.rounds} rounds)...", flush=True)
    print(f"{DIM}Each round: dialog phase (Grok) → decisions → payoffs → state update{RESET}\n", flush=True)

    # Monkey-patch run_simulation to get per-round live output
    from simulation import game_engine as _ge
    original_run = _ge.run_simulation

    # We run simulation normally but intercept round results via a wrapper
    # that prints after each round completes
    import functools

    names = {a.agent_id: a.name for a in agents if a.name}

    class LiveGameResult:
        """Wrapper that prints live output as each round completes."""

        def __init__(self, total_rounds, prev_snaps, agent_ids_list, agent_names, agent_cores):
            self.total_rounds = total_rounds
            self.prev_snaps = prev_snaps
            self.agent_ids = agent_ids_list
            self.names = agent_names
            self.cores = agent_cores
            self.story_params = None  # set after run_simulation populates it

        def on_round(self, round_result):
            rn = round_result.round_number

            # ── World Engine structured event (для WE tab в браузері) ──
            emit_we_event(round_result, self.agent_ids, self.names,
                          self.total_rounds, self.story_params, self.cores)

            # ── 1. СИТУАЦІЯ + РЕФЛЕКСІЯ ──────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  СИТУАЦІЯ")
            print_situation_and_reflections(round_result, self.agent_ids, self.names)

            # ── 2. ДІАЛОГ ────────────────────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  ДІАЛОГ")
            print_round_dialog(round_result, self.agent_ids, self.names)

            # ── 3. REASONING (думки агентів) ─────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  REASONING")
            print_reasoning(round_result, self.agent_ids, self.names)

            # ── 4. РІШЕННЯ + BREAKDOWN ────────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  РІШЕННЯ")
            print_decision_breakdown(round_result, self.agent_ids, self.names, self.cores)

            # ── 5. ВИПЛАТИ ───────────────────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  ВИПЛАТИ")
            print_payoffs(round_result, self.agent_ids, self.names)

            # ── 6. НАРАТИВ (storytelling) ─────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  НАРАТИВ")
            print_narrative(round_result)

            # ── 7. ЗМІНИ СТАНУ ────────────────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  ЗМІНИ СТАНУ")
            print_state_changes(round_result, self.prev_snaps, self.agent_ids, self.names)

            # ── 8. РЕФЛЕКСІЇ (нотатки в пам'ять) ─────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  РЕФЛЕКСІЇ")
            print_reflections(round_result, self.agent_ids, self.names)

            # ── 9. SOCIAL FABRIC ──────────────────────────────────────
            header(f"РАУНД {rn}/{self.total_rounds}  ·  SOCIAL FABRIC")
            print_social_fabric(round_result, self.agent_ids, self.names)

            # Update prev snapshots for next round diff
            self.prev_snaps = dict(round_result.state_snapshots)

            print(flush=True)

    # Build cores dict for decision breakdown display
    # Priority: disk CORE.json → in-memory agent.core (synth agents)
    agent_cores = {}
    for a in agents:
        try:
            import json as _json
            core_path = ROOT / "agents" / a.agent_id / "CORE.json"
            if core_path.exists():
                agent_cores[a.agent_id] = _json.loads(core_path.read_bytes().decode("utf-8"))
        except Exception:
            pass
        # Fallback: use in-memory core (synthetic agents defined in SYNTH_AGENT_CONFIGS)
        if a.agent_id not in agent_cores and hasattr(a, "core") and a.core:
            agent_cores[a.agent_id] = dict(a.core)

    live = LiveGameResult(args.rounds, prev_snapshots, agent_ids, names, agent_cores)

    # Patch run_simulation so on_round fires IMMEDIATELY when each round completes
    # (not after all rounds like before). Key: hook into on_progress "complete" event
    # which fires right after result.rounds.append(round_result) in game_engine.py
    _sim_result_holder = [None]

    def patched_run(agents_list, total_rounds=10, model="google/gemini-2.0-flash-001",
                    use_dialog=True, simulation_id=None, reveal_requests=None,
                    story_params_override=None, verbose=False, on_progress=None):
        result = original_run(
            agents_list,
            total_rounds=total_rounds,
            model=model,
            use_dialog=use_dialog,
            simulation_id=simulation_id,
            reveal_requests=reveal_requests,
            story_params_override=story_params_override,
            verbose=verbose,
            on_progress=on_progress,
        )
        _sim_result_holder[0] = result
        return result

    # Live progress callback — prints to terminal immediately as each phase completes
    _phase_start = [time.time()]  # mutable container for closure
    _round_start = [time.time()]

    def live_progress(event: str, round_result=None):
        parts = event.split(":")
        if len(parts) < 4:
            return
        rnum, total, stage = int(parts[1]), int(parts[2]), parts[3]
        now = time.time()
        elapsed = now - _phase_start[0]
        _phase_start[0] = now

        if stage == "dialog_start":
            _current_round_num[0] = rnum   # track for LLM_EVENT emitter
            _phase_start[0] = now
            _round_start[0] = now
            if args.verbose:
                print(f"\n{DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}", flush=True)
                print(f"  {DIM}Round {rnum}/{total}{RESET}  {BOLD}DIALOG{RESET}", flush=True)
            else:
                print(f"  {DIM}Round {rnum}/{total}{RESET}  dialog...", end="", flush=True)
        elif stage == "dialog_done":
            if args.verbose:
                print(f"  {DIM}dialog done ({elapsed:.1f}s){RESET}  {BOLD}REASONING{RESET} (parallel)", flush=True)
            else:
                print(f" {DIM}({elapsed:.1f}s){RESET}  reasoning...", end="", flush=True)
        elif stage == "reasoning_done":
            if args.verbose:
                print(f"  {DIM}reasoning done ({elapsed:.1f}s){RESET}  {BOLD}DECISIONS{RESET}", flush=True)
            else:
                print(f" {DIM}({elapsed:.1f}s){RESET}  decisions...", end="", flush=True)
        elif stage == "decisions_done":
            if args.verbose:
                print(f"  {DIM}decisions done ({elapsed:.1f}s){RESET}  {BOLD}PAYOFFS + REFLECTIONS{RESET} (parallel)", flush=True)
            else:
                print(f" {DIM}({elapsed:.1f}s){RESET}  payoffs...", end="", flush=True)
        elif stage == "complete":
            total_round_time = now - _round_start[0]
            if args.verbose:
                print(f"  {DIM}payoffs+reflections done ({elapsed:.1f}s){RESET}  {GREEN}✓ round {rnum} total: {total_round_time:.1f}s{RESET}", flush=True)
            else:
                print(f" {DIM}({elapsed:.1f}s){RESET}  {GREEN}✓{RESET}\n", flush=True)

            # ── REAL-TIME: render this round immediately ──
            # round_result is passed directly from game_engine.py
            if round_result is not None:
                live.on_round(round_result)

    # Since run_simulation runs all rounds internally, we call it directly
    # and then render each round from the result
    mode_label = "verbose" if args.verbose else "fast"
    print(f"{DIM}Running simulation with Gemini Flash ({mode_label})...{RESET}\n", flush=True)
    t_start = time.time()

    from simulation.game_engine import run_simulation
    from storytell.story_params import StoryParams

    story_override = None
    if (args.setup or "").strip().lower() == "mars":
        story_override = StoryParams(
            seed=0,
            year="2040",
            place="база на Марсі",
            setup="колонізація Марса",
            problem="обмежені ресурси, довіра між колоністами",
            characters=["командир", "інженер", "медик", "біолог"],
            genre="survival",
            mood="tense",
            stakes="виживання",
        )
    elif (args.world_prompt or "").strip():
        story_override = StoryParams(
            seed=0,
            year="сучасність",
            place="невідоме місце",
            characters=[],
            setup=args.world_prompt.strip(),
            problem=args.world_prompt.strip(),
        )

    # Pre-set story_params NOW (after story_override is defined).
    # emit_we_event fires DURING simulation, so we pass the known override immediately.
    if story_override:
        live.story_params = story_override

    # Store result reference in holder so live_progress "complete" can access it
    _sim_result_holder[0] = type('_R', (), {'rounds': []})()  # empty placeholder

    # ── Monkey-patch call_openrouter to capture all LLM I/O ──────────────────
    import pipeline.seed_generator as _seed_gen
    _orig_call_openrouter = _seed_gen.call_openrouter

    def _patched_call_openrouter(
        system_prompt: str,
        user_prompt: str,
        model: str = "openai/gpt-4o-mini",
        temperature: float = 0.85,
        max_tokens: int = 300,
        timeout: int = 120,
        json_schema=None,
        api_key=None,
    ) -> str:
        response = _orig_call_openrouter(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            json_schema=json_schema,
            api_key=api_key,
        )
        try:
            phase = _llm_detect_phase(system_prompt)
            aid, aname = _llm_detect_agent(system_prompt, user_prompt, names)
            emit_llm_event(
                phase=phase,
                agent_id=aid,
                agent_name=aname,
                system=system_prompt,
                user=user_prompt,
                response=response or "",
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                has_schema=(json_schema is not None),
                total_rounds=args.rounds,
            )
        except Exception:
            pass  # never break simulation due to logging
        return response

    _seed_gen.call_openrouter = _patched_call_openrouter

    def _on_progress_with_sp(event: str, round_result=None):
        live_progress(event, round_result)

    result = run_simulation(
        agents,
        total_rounds=args.rounds,
        model="google/gemini-2.0-flash-001",
        use_dialog=True,
        simulation_id="live_run",
        on_progress=_on_progress_with_sp,
        verbose=args.verbose,
        story_params_override=story_override,
    )

    # Backfill story_params from result (available after simulation completes)
    # This is fine since story_params is static across rounds
    if hasattr(result, "story_params") and result.story_params:
        from storytell.story_params import StoryParams
        try:
            sp = result.story_params
            live.story_params = StoryParams(
                seed=0,
                year=sp.get("year", ""),
                place=sp.get("place", ""),
                characters=sp.get("characters", []),
                setup=sp.get("setup", ""),
                problem=sp.get("problem", ""),
                genre=sp.get("genre", "drama"),
                mood=sp.get("mood", "tense"),
                stakes=sp.get("stakes", ""),
            )
        except Exception:
            pass

    elapsed = time.time() - t_start
    print(flush=True)

    # Final results
    print(f"\n{BOLD}{'═'*54}{RESET}", flush=True)
    print(f"{BOLD}  FINAL RESULTS  ({elapsed:.0f}s elapsed){RESET}", flush=True)
    print(f"{BOLD}{'═'*54}{RESET}\n", flush=True)

    sorted_scores = sorted(result.final_scores.items(), key=lambda x: -x[1])
    max_score = sorted_scores[0][1] if sorted_scores else 1.0

    for i, (aid, score) in enumerate(sorted_scores):
        b = bar(max(0.0, score / max(max_score, 1.0)))
        agent = next((a for a in agents if a.agent_id == aid), None)
        mood = agent.states.mood if agent else "?"
        mc = mood_color(mood)
        medal = ["🥇", "🥈", "🥉", " 4"][min(i, 3)]
        disp_name = names.get(aid, aid[-12:])
        winner_mark = f"  {BOLD}{GREEN}← WINNER{RESET}" if i == 0 else ""
        print(
            f"  {medal}  {BOLD}{disp_name:8s}{RESET}  {DIM}{aid[-12:]:12s}{RESET}  {score:+8.2f}  {b}  {mc}{mood}{RESET}{winner_mark}",
            flush=True,
        )

    winner_name = names.get(result.winner, result.winner)
    print(f"\n  Winner: {BOLD}{GREEN}{winner_name}{RESET}", flush=True)

    # Score range context
    sr = result.score_range()
    print(f"\n  {DIM}Score context ({sr['n_rounds']} rounds, {sr['n_agents']} agents):", flush=True)
    print(f"  Max possible (always exploit): {sr['max_possible']:+.1f}", flush=True)
    print(f"  Mutual coop:                   {sr['mutual_coop_score']:+.1f}", flush=True)
    print(f"  Mutual defect:                 {sr['mutual_defect_score']:+.1f}", flush=True)
    print(f"  Min possible (always sucker):  {sr['min_possible']:+.1f}{RESET}", flush=True)
    print(flush=True)

    # Update agent stats (persist across games)
    try:
        from agents.stats import update_after_game
        update_after_game(
            agent_ids=result.agent_ids,
            agent_names=result.agent_names,
            final_scores=result.final_scores,
            winner_id=result.winner,
            game_id=result.simulation_id,
            rounds_played=len(result.rounds),
        )
    except Exception as _e:
        if args.verbose:
            print(f"  {DIM}[stats] update failed: {_e}{RESET}", flush=True)

    # HTML / JSON export
    if args.html:
        from export_game_log import export_to_html
        from datetime import datetime as _dt
        logs_dir = ROOT / "logs" / "island"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Filename: game_YYYY-MM-DD_HH-MM-SS_<name>.json/html (name required for /api/games-summary regex)
        ts = _dt.now().strftime("%Y-%m-%d_%H-%M-%S")
        name_part = f"_{args.name}" if args.name else "_island"
        log_basename = f"game_{ts}{name_part}"

        # Build extended log with reflections and conclusions
        extended_log = result.to_dict()
        extended_log["score_range"] = sr

        # Collect per-round notes, situation reflections, and reasoning from RoundResult
        agent_reflections = {a.agent_id: [] for a in agents}
        agent_situation_reflections = {a.agent_id: [] for a in agents}
        agent_reasonings = {a.agent_id: [] for a in agents}
        for rr in result.rounds:
            for aid in agent_reflections:
                note = rr.notes.get(aid, "")
                if note:
                    agent_reflections[aid].append({"round": rr.round_number, "notes": note})
                sit_note = getattr(rr, "situation_reflections", {}).get(aid, "")
                if sit_note:
                    agent_situation_reflections[aid].append({"round": rr.round_number, "notes": sit_note})
                reasoning = rr.reasonings.get(aid)
                if reasoning:
                    agent_reasonings[aid].append({"round": rr.round_number, "reasoning": reasoning})

        extended_log["agent_reflections"] = agent_reflections
        extended_log["agent_situation_reflections"] = agent_situation_reflections

        # Collect post-game conclusions from game_history
        extended_log["game_conclusions"] = {}
        for a in agents:
            if a.memory.game_history:
                last = a.memory.game_history[-1]
                if last.get("conclusion"):
                    extended_log["game_conclusions"][a.agent_id] = last["conclusion"]

        extended_log["agent_reasonings"] = agent_reasonings

        # Agent stats (cumulative across games)
        try:
            from agents.stats import load_stats
            stats_data = load_stats()
            extended_log["agent_stats"] = stats_data.get("agents", {})
        except Exception:
            extended_log["agent_stats"] = {}

        # Agent profiles (connections, profession, bio) from roster; enrich bio from BIO.md if present
        roster_path = ROOT / "agents" / "roster.json"
        agent_profiles = {}
        if roster_path.exists():
            roster = __import__("json").loads(roster_path.read_text(encoding="utf-8"))
            for a in roster.get("agents", []):
                aid = a.get("id")
                if aid in result.agent_ids and a.get("profile"):
                    agent_profiles[aid] = dict(a["profile"])
        # Override or set bio from agents/{id}/BIO.md
        for aid in list(agent_profiles.keys()):
            bio_path = ROOT / "agents" / aid / "BIO.md"
            if bio_path.exists():
                agent_profiles[aid]["bio"] = bio_path.read_text(encoding="utf-8").strip()
        extended_log["agent_profiles"] = agent_profiles

        json_path = logs_dir / f"{log_basename}.json"
        json_path.write_text(
            __import__("json").dumps(extended_log, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  JSON log: {json_path}", flush=True)

        html_path = logs_dir / f"{log_basename}.html"
        export_to_html(extended_log, output_path=html_path)
        print(f"  HTML log: {html_path}", flush=True)
        print(f"\n  {BOLD}{GREEN}Open in browser:{RESET} open \"{html_path}\"", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
