# Sua IA escreveu a query. Quem mediu?

> Rascunho Etapa 3 (PT-BR) · ~1.400 palavras · números só de logs medidos  
> Fonte dos números da demo: `examples/demo_fastapi/optimization_log.md` + `runs/sqlite/latest.json` (PR Phase 0 / Etapa 1).  
> Caso Radar: só o publicável — ainda `[MEDIR]` até a Etapa 2 fechar a tabela anonimizada.

Você abriu o PR. Os testes passaram. O endpoint devolve JSON limpo. E mesmo assim a rota é lenta.

Não é mistério de “o ORM é lento”. Em geral a query está **correta** e **cega ao banco**: sem índice no filtro certo, N+1 escondido no lazy load, insert linha a linha. Detectores sugerem. O que falta — e o que este texto defende — é um freio de mão com número: **contar → medir → mudar uma coisa → medir de novo → gravar o log**.

## Por que código de IA/ORM fica lento (sem inventar frequência)

Ferramentas de mercado e papers apontam o padrão: LLMs acertam a semântica e erram a eficiência ([EESQLBench](https://doi.org/10.1145/3832269)); revisões de PR de IA relatam mais I/O excessivo, com poucas regressões de latência “clássicas” em volume ([CodeRabbit](https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report)). Não há fonte sólida para “X% dos N+1 vêm de IA” — então **não citamos um**.

O diferencial útil não é mais um linter: é a skill/CLI que **não aceita “ficou mais rápido” sem prova**.

## O que é o db-route-optimizer

Skill de Claude Code + scripts Python (MIT, open source, **não é produto pago**):

1. Provar o problema (`querycount` / `EXPLAIN`)
2. Baseline (`bench` mediana + p95)
3. Uma mudança
4. Candidate
5. Comparar e anexar ao `optimization_log.md`
6. Verificar igualdade (hash da resposta / testes)

Instalação (quando a v0.1.0 estiver no `main` — hoje na branch `feat/phase0-python-mvp`):

```bash
# skill
git clone https://github.com/Mean-Says/db-route-optimizer.git ~/.claude/skills/db-route-optimizer

# CLI
pipx install .
# ou: uv tool install .
dbro-querycount
dbro-bench --help
dbro-explain --help
```

## Antes/depois medidos (demo FastAPI, SQLite)

Protocolo: `--seed 42`, warmup 5, n 30, uma mudança por cenário, igualdade por hash. Ambiente completo no JSON do run (Python 3.12.3, Linux x86_64, seed users=200 / posts=1000 / products=5000, `seed_seconds≈0.16`).

Fonte: [optimization_log.md](https://github.com/Mean-Says/db-route-optimizer/blob/feat/phase0-python-mvp/examples/demo_fastapi/optimization_log.md) (branch Etapa 1 até o merge).

| Cenário | Métrica | Antes | Depois | Ganho |
|---------|---------|------:|-------:|------:|
| N+1 → `selectinload` | queries/request | 51 | 2 | — |
| N+1 → `selectinload` | mediana (ms) | 12.87 | 6.79 | 47.24% · 1.90× |
| N+1 → `selectinload` | p95 (ms) | 22.51 | 7.50 | 66.68% · 3.00× |
| Insert linha a linha → bulk | mediana (ms) | 133.45 | 12.29 | 90.79% · 10.86× |
| Insert linha a linha → bulk | p95 (ms) | 177.38 | 14.10 | 92.05% · 12.58× |
| Índice em filtro/ordem | mediana (ms) | 4.57 | 4.34 | 5.03% · 1.05× |

No cenário de índice, o ganho de latência no SQLite com 5k linhas foi pequeno; o log JSON guarda a entrada de `--suggest-index --verify`. Em Postgres o plano costuma falar mais alto — `[MEDIR: runs/postgres após make reproduce com Docker]`.

Uma segunda execução SQLite manteve os **mesmos vereditos** (N+1 e batch claramente melhores; igualdade ok). Ms absolutos variam; o veredito não inventamos.

## O protocolo (curto)

1. Fixture com cardinalidade declarada e seed fixo — dado de brinquedo não vale.
2. Mesmo ambiente; warmup ≥ 5; n ≥ 30; mediana e p95.
3. Uma mudança por comparação.
4. Corretude: hash igual (ou testes); sem isso não é “melhorou”.
5. Tudo no log com SHA do git e ambiente.
6. Nunca bench de escrita/DDL/`EXPLAIN ANALYZE` em produção.

## Caso real: Radar de Empregos

O plano usa o Radar (FastAPI + Postgres na VPS) como campo: cópia sanitizada local, alvos por `pg_stat_statements`, ≥3 otimizações medidas em log **privado**, e só uma fatia anonimizada no artigo.

**Ainda não medido publicamente.** Sem dump sanitizado nem checkout do app fechado neste ambiente. Playbook público: `docs/radar/` (PR Etapa 2). Tabela publicável:

| Métrica | Antes | Depois | Ganho |
|---------|------:|-------:|------:|
| Queries/request | [MEDIR: Radar] | [MEDIR] | — |
| p50 | [MEDIR] | [MEDIR] | [MEDIR] |
| p95 | [MEDIR] | [MEDIR] | [MEDIR] |
| Forma do plano | [MEDIR] | [MEDIR] | — |
| Ambiente (ordem de grandeza) | [MEDIR] | | |

Até o Rafael revisar a tabela anonimizada, o artigo **não** cita nomes de tabelas, SQL literal nem contagens exatas de produção.

## Limites (honestos)

- Contador de queries maduro para SQLAlchemy; outros stacks via referências.
- Sem HypoPG/Dexter/MCP de terceiros — capacidades próprias.
- Sugestão de índice só vira recomendação depois de criar na cópia e re-medir.
- Demo Postgres do `make reproduce` completo: `[MEDIR]` até rodar com Docker.

## Como contribuir

Repo: https://github.com/Mean-Says/db-route-optimizer (MIT). Issues “good first” depois da v0.1.0. Divulgação em listagens de skills fica **depois** deste artigo publicado (Etapa 3 do plano).

Medir → mudar → medir → registrar. Sem número no log, não é otimização — é achismo.
