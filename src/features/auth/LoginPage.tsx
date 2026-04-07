import { type FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { LanguageSwitcher } from "../../app/layout/LanguageSwitcher";
import { useAppState } from "../../app/state/app-state";
import { BrandMark, LockIcon, MailIcon } from "../../components/AppIcons";
import { getMessages } from "../../i18n/messages";

interface LoginLocationState {
  from?: string;
  protected?: boolean;
}

export function LoginPage() {
  const { locale, session, signIn } = useAppState();
  const messages = getMessages(locale).auth;
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("demo@financehub.com");
  const [password, setPassword] = useState("demo1234");
  const [returnToRequestedRoute, setReturnToRequestedRoute] = useState(false);

  const locationState = location.state as LoginLocationState | null;
  const redirectTo = locationState?.from ?? "/";
  const isProtectedRedirect = locationState?.protected === true;

  if (session) {
    return <Navigate replace to={returnToRequestedRoute || isProtectedRedirect ? redirectTo : "/"} />;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedEmail = email.trim();
    const normalizedPassword = password.trim();
    if (!normalizedEmail || !normalizedPassword) {
      return;
    }

    setReturnToRequestedRoute(true);
    signIn({ email: normalizedEmail });
    navigate(redirectTo, { replace: true });
  };

  const handleDemoSignIn = () => {
    setReturnToRequestedRoute(true);
    signIn({ email: "demo@financehub.com" });
    navigate(redirectTo, { replace: true });
  };

  const highlights = [
    messages.highlightMarkets,
    messages.highlightData,
    messages.highlightInsights,
  ];

  return (
    <main className="login-page">
      <section className="login-page__panel" aria-labelledby="login-title">
        <div className="login-page__badge">
          <BrandMark className="login-page__badge-icon" />
          <span>FinanceHub</span>
        </div>
        <article className="login-card">
          <div className="login-card__header">
            <div>
              <h1 id="login-title">{messages.title}</h1>
              <p>{messages.subtitle}</p>
            </div>
            <LanguageSwitcher />
          </div>
          <form className="login-card__form" onSubmit={handleSubmit}>
            <label className="login-field">
              <span>{messages.emailLabel}</span>
              <span className="login-field__control">
                <MailIcon className="login-field__icon" />
                <input
                  aria-label={messages.emailLabel}
                  onChange={(event) => setEmail(event.target.value)}
                  type="email"
                  value={email}
                />
              </span>
            </label>
            <label className="login-field">
              <span>{messages.passwordLabel}</span>
              <span className="login-field__control">
                <LockIcon className="login-field__icon" />
                <input
                  aria-label={messages.passwordLabel}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                  value={password}
                />
              </span>
            </label>
            <button className="login-card__primary-action" type="submit">
              {messages.signInAction}
            </button>
            <button className="login-card__secondary-action" onClick={handleDemoSignIn} type="button">
              {messages.demoAction}
            </button>
          </form>
        </article>
        <section className="login-highlights">
          {highlights.map((highlight) => (
            <article className="login-highlights__card" key={highlight}>
              <p>{highlight}</p>
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}
