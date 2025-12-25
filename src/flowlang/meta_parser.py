# -*- coding: utf-8 -*-
# file: src/flowlang/meta_parser.py
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional, List

from .meta_model import (
    MetaWorld,
    MetaDomain,
    MetaDSL,
    MetaEffect,
    MetaAgentClass,
    MetaPlanClass,
)

_COMMENT_RE = re.compile(r"\s*(#|//).*?$")


def _strip_comments(line: str) -> str:
    """Убираем # и // комментарии в конце строки."""
    return _COMMENT_RE.sub("", line).rstrip()


def parse_meta_world(text: str) -> MetaWorld:
    """
    Минималистичный парсер FlowMeta.

    Ожидаемый синтаксис (как в нашем flowmeta.meta):

        world foxproflow {

          domains {
            logistics {
              dsl "autoplan"  { files = "flow/autoplan/*.flow" }
              dsl "etl"       { files = "flow/etl/*.flow"      }
            }

            dev {
              dsl "dev"       { files = "flow/dev/*.flow"      }
            }

            security {
              dsl "flowsec"   { files = "flow/security/*.flow" }
            }
          }

          effects {
            effect DbRead { kind="db"; scope=["public.*"] }
            ...
          }

          agent_class AutoplanAgent {
            domain = "logistics"
            dsl    = "autoplan"
            allow  = [DbRead, DbWrite, OSRMRoute]
            deny   = [NetExt]
          }

          plan_class AutoplanPlan {
            dsl             = "autoplan"
            default_effects = [DbRead, OSRMRoute]
          }
        }
    """
    lines = [_strip_comments(l) for l in text.splitlines()]
    # убираем пустые строки
    raw_lines = [l for l in lines if l.strip()]

    # ---------- world ----------
    world_name: Optional[str] = None
    for l in raw_lines:
        m = re.match(r"\s*world\s+([A-Za-z0-9_]+)", l)
        if m:
            world_name = m.group(1)
            break

    if not world_name:
        raise ValueError("FlowMeta: не найдено объявление world <name> {...}")

    # NB: в MetaWorld поле называется world_name, а не name
    world = MetaWorld(world_name=world_name)

    # ---------- domains / dsl ----------
    in_domains = False
    current_domain: Optional[str] = None

    for raw in raw_lines:
        line = raw.strip()
        if not line:
            continue

        if not in_domains and line.startswith("domains"):
            in_domains = True
            current_domain = None
            continue

        if in_domains:
            if line == "}":
                # либо закрыли домен, либо блок domains целиком
                if current_domain is not None:
                    current_domain = None
                else:
                    in_domains = False
                continue

            if current_domain is None:
                # ожидаем "<domain> {"
                m_dom = re.match(r"([A-Za-z0-9_]+)\s*\{", line)
                if m_dom:
                    current_domain = m_dom.group(1)
                    # если домена ещё нет — создаём
                    if current_domain not in world.domains:
                        world.add_domain(
                            MetaDomain(
                                code=current_domain,
                                description=None,
                            )
                        )
                continue

            # внутри домена — строки dsl "name" { files = "..." }
            m_dsl = re.match(
                r'dsl\s+"([^"]+)"\s*\{\s*files\s*=\s*"([^"]+)"\s*\}?', line
            )
            if m_dsl and current_domain:
                dsl_code = m_dsl.group(1)
                files_glob = m_dsl.group(2)

                dsl_obj = MetaDSL(
                    code=dsl_code,
                    domain=current_domain,
                    files_pattern=files_glob,
                )
                world.add_dsl(dsl_obj)
                continue

    # ---------- effects ----------
    effect_line_re = re.compile(
        r'^\s*effect\s+([A-Za-z0-9_]+)\s*\{(.*)\}\s*$'
    )
    for raw in raw_lines:
        line = raw.strip()
        m_eff = effect_line_re.match(line)
        if not m_eff:
            continue

        code = m_eff.group(1)
        body = m_eff.group(2)

        kind = ""
        scope_list: List[str] = []

        m_kind = re.search(r'kind\s*=\s*"([^"]+)"', body)
        if m_kind:
            kind = m_kind.group(1)

        m_scope = re.search(r"scope\s*=\s*\[([^\]]*)\]", body)
        if m_scope:
            items = m_scope.group(1).split(",")
            scope_list = [
                x.strip().strip('"').strip("'")
                for x in items
                if x.strip()
            ]

        eff_obj = MetaEffect(
            code=code,
            kind=kind,
            scope=scope_list,
        )
        world.add_effect(eff_obj)

    # ---------- agent_class ----------
    agent_name: Optional[str] = None
    agent_domain: Optional[str] = None
    agent_dsl: Optional[str] = None
    agent_allow: List[str] = []
    agent_deny: List[str] = []

    for raw in raw_lines:
        line = raw.strip()
        if not agent_name:
            m_start = re.match(
                r"agent_class\s+([A-Za-z0-9_]+)\s*\{", line
            )
            if m_start:
                agent_name = m_start.group(1)
                agent_domain = None
                agent_dsl = None
                agent_allow = []
                agent_deny = []
            continue

        # внутри блока agent_class
        if line == "}":
            # закрываем блок
            if agent_name:
                ac = MetaAgentClass(
                    code=agent_name,
                    domain=agent_domain or "",
                    dsl_code=agent_dsl,
                    allow_effects=agent_allow,
                    deny_effects=agent_deny,
                )
                world.add_agent_class(ac)
            agent_name = None
            continue

        m_dom = re.match(r'domain\s*=\s*"([^"]+)"', line)
        if m_dom:
            agent_domain = m_dom.group(1)
            continue

        m_dsl = re.match(r'dsl\s*=\s*"([^"]+)"', line)
        if m_dsl:
            agent_dsl = m_dsl.group(1)
            continue

        m_allow = re.match(r"allow\s*=\s*\[([^\]]*)\]", line)
        if m_allow:
            raw_items = m_allow.group(1).split(",")
            agent_allow = [
                x.strip().strip('"').strip("'")
                for x in raw_items
                if x.strip()
            ]
            continue

        m_deny = re.match(r"deny\s*=\s*\[([^\]]*)\]", line)
        if m_deny:
            raw_items = m_deny.group(1).split(",")
            agent_deny = [
                x.strip().strip('"').strip("'")
                for x in raw_items
                if x.strip()
            ]
            continue

    # ---------- plan_class ----------
    plan_name: Optional[str] = None
    plan_dsl: Optional[str] = None
    plan_default_effects: List[str] = []

    for raw in raw_lines:
        line = raw.strip()
        if not plan_name:
            m_start = re.match(
                r"plan_class\s+([A-Za-z0-9_]+)\s*\{", line
            )
            if m_start:
                plan_name = m_start.group(1)
                plan_dsl = None
                plan_default_effects = []
            continue

        if line == "}":
            if plan_name:
                pc = MetaPlanClass(
                    code=plan_name,
                    dsl_code=plan_dsl or "",
                    default_effects=plan_default_effects,
                )
                world.add_plan_class(pc)
            plan_name = None
            continue

        m_dsl = re.match(r'dsl\s*=\s*"([^"]+)"', line)
        if m_dsl:
            plan_dsl = m_dsl.group(1)
            continue

        m_def = re.match(
            r"default_effects\s*=\s*\[([^\]]*)\]", line
        )
        if m_def:
            raw_items = m_def.group(1).split(",")
            plan_default_effects = [
                x.strip().strip('"').strip("'")
                for x in raw_items
                if x.strip()
            ]
            continue

    return world


def load_meta_world(path: Path) -> MetaWorld:
    text = path.read_text(encoding="utf-8")
    return parse_meta_world(text)


def main(argv: Optional[list[str]] = None) -> None:
    """
    CLI:
        python -m src.flowlang.meta_parser
        python -m src.flowlang.meta_parser config/flowmeta/flowmeta.meta
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        path = Path(argv[0])
    else:
        path = Path("config/flowmeta/flowmeta.meta")

    world = load_meta_world(path)
    print(json.dumps(world.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
