import { NavLink } from "react-router-dom";

import { getMessages, routeDefinitions } from "../../i18n/messages";
import { useAppState } from "../state/app-state";

export function SidebarNav() {
  const { locale } = useAppState();
  const messages = getMessages(locale);

  return (
    <aside className="app-sidebar">
      <nav aria-label="Primary" className="app-sidebar__nav">
        {routeDefinitions.map((route) => (
          <NavLink
            className={({ isActive }) =>
              isActive ? "app-sidebar__link is-active" : "app-sidebar__link"
            }
            end={route.path === "/"}
            key={route.key}
            to={route.path}
          >
            {messages.nav[route.key].title}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
