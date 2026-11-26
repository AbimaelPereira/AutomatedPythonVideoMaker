---
name: feature
description: Fluxo completo de desenvolvimento de uma feature no monorepo - planner, devs em paralelo, qa. Use quando o usuário pedir /feature ou pedir para implementar uma funcionalidade que envolva api, videomaker, web ou banco.
---
# /feature <descrição>

1. **Planejar**: chame o agente `planner` com a descrição. Mostre ao usuário o resumo do contrato gerado em `docs/contracts/` e espere o OK.
2. **Branch de trabalho**: se estiver na `main`, crie `feature/<slug>` (`git switch -c`). Tudo da feature fica nela.
3. **Banco primeiro**: se o plano tiver tarefa de `db-migration`, rode-a **sem worktree**, na branch de trabalho. Ao terminar, faça um commit local com a migration + `models.py` (`db: <descrição>`).
   Motivo: worktrees nascem do último commit; sem esse commit os devs não enxergam a migration nem o model novo.
4. **Implementar**: chame `api-dev`, `videomaker-dev`, `web-dev` (só os do plano) em paralelo, cada um com `isolation: "worktree"`, passando o caminho do contrato e a tarefa dele. Cada um roda `bash .claude/scripts/worktree-setup.sh` no início e commita no próprio branch no fim.
5. **Juntar**: `git merge` dos branches dos worktrees na branch de trabalho; resolva conflitos.
6. **QA**: chame `qa`. Se `REPROVADO`, devolva os problemas ao dev responsável e repita até `APROVADO` (máx. 3 rodadas; depois pare e mostre ao usuário).
   Correção de migration desta feature: o `db-migration` pode editá-la (ainda não está na `main`), seguindo "Corrigir migration da feature" do `database/README.md`.
7. **Fim**: resumo curto (o que mudou, testes, migrations aplicadas). Commits só locais na branch `feature/<slug>`: NÃO faça push nem merge na `main` — o usuário decide.
   Mensagens de commit sem linha `Co-Authored-By`.
