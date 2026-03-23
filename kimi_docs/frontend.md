# Frontend (Next.js 14)

## App Structure (`frontend/src`)
- `app/`: app router pages (dashboard at `page.tsx`, subroutes: `backtest/`, `login/`, `orders/`, `portfolio/`, `register/`, `risk/`, `settings/`, `signals/`). Shared layout in `layout.tsx`, globals in `app/globals.css`.
- `components/`: UI building blocks and layouts.
  - `components/dashboard/stats.tsx`: dashboard cards; shows initial capital, equity, cash, P&L metrics, daily P&L, open positions.
  - `components/layout/`: wrappers for navigation/layout.
  - `components/ui/`: design system primitives (Card, Table, Badge, etc.).
  - `components/providers.tsx`: React Query + theme providers.
- `hooks/`: data hooks powered by React Query.
  - `use-portfolio.ts`: fetch positions, summary, pnl.
  - `use-orders.ts`: fetch/create/cancel orders; run paper trader; invalidates related queries.
  - Other hooks for auth, signals, etc. (pattern similar: `useQuery`/`useMutation`).
- `lib/api.ts`: axios client with baseURL `NEXT_PUBLIC_API_URL` + `/api/v1`; attaches bearer token from localStorage; refreshes token on 401; exposes typed API helpers (auth, market, orders, paper, portfolio, backtest, risk).
- `types/`: shared TypeScript interfaces (not all enumerated).

## Data Fetching
- React Query caches by keys: `orders`, `positions`, `portfolio-summary`, `pnl`, `signals`, etc.
- Mutations invalidate caches to refresh UI after actions (order create/cancel, paper run).

## Auth
- Tokens stored in localStorage (`access_token`, `refresh_token`); axios interceptor refreshes on 401 via `/auth/refresh`.
- Login/Register pages call `authApi.login/register` and set tokens client-side.

## Pages of note
- `app/page.tsx`: main dashboard with stats component.
- `app/orders/page.tsx`: order list + “Run Paper Trader” button using `useOrders().runPaperTrader`.
- `app/portfolio/page.tsx`: summary cards (equity, cash, P&L, P&L %), positions table with P&L coloring.
- `app/signals/page.tsx`: trigger paper trader, view signals.

## Styling
- TailwindCSS configured via `tailwind.config.js`, `globals.css`. Icons from `lucide-react`.

## Dev Server
- Run `npm install`, then `npm run dev -- --port 3002` (3000/3001 may be busy). Ensure `NEXT_PUBLIC_API_URL=http://localhost:8000`.
