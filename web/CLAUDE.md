# web/

- React 18 + TypeScript + Vite + Tailwind; ícones `lucide-react`; rotas `react-router-dom`.
- HTTP só por `src/services/api.ts` (axios, baseURL `/api`, proxy do Vite para a api).
- Estrutura: `pages/<área>/`, componentes compartilhados em `components/` e `components/ui/`, estado global em `contexts/` (Auth, Toast).
- Validar com `npm run build` (roda `tsc`).
- Rodar: `npm install` · `npm run dev` (porta 5173).
