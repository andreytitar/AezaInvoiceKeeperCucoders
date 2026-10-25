import { Outlet, useLocation } from 'react-router-dom'

/** Короткое появление при смене раздела (150–200 ms, см. DESIGN.md). */
export function PageEnter() {
  const { pathname } = useLocation()
  return (
    <div key={pathname} className="page-enter">
      <Outlet />
    </div>
  )
}
