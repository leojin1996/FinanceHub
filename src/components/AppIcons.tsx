import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function BaseIcon({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="16"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.6"
      viewBox="0 0 16 16"
      width="16"
      {...props}
    >
      {children}
    </svg>
  );
}

export function BrandMark(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.4"
      viewBox="0 0 20 20"
      width="20"
      {...props}
    >
      <circle cx="10" cy="10" r="8" />
      <path d="M6 12.5V7.5l4-2 4 2v5l-4 2-4-2Z" />
      <path d="M10 5.5v9" />
    </svg>
  );
}

export function MarketIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M2 13h12" />
      <path d="m3.5 10 2-2 2.2 1.6L11.8 5 13 6.2" />
    </BaseIcon>
  );
}

export function StocksIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect height="9" rx="1.2" width="10" x="3" y="3.5" />
      <path d="M3 8h10" />
      <path d="M6.2 12.5v1.5" />
      <path d="M9.8 12.5v1.5" />
    </BaseIcon>
  );
}

export function IndicesIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3 12.5V7.8" />
      <path d="M7 12.5V5.2" />
      <path d="M11 12.5v-3.7" />
      <path d="M13.5 4.5 2.5 12" />
    </BaseIcon>
  );
}

export function RiskIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M8 2.5 13 4.2v3.9c0 2.4-1.2 4.6-3 5.9-1.8-1.3-3-3.5-3-5.9V4.2L8 2.5Z" />
      <path d="M8 6.3v3.2" />
      <path d="M8 11.5h0" />
    </BaseIcon>
  );
}

export function RecommendationIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="m8 2.5 1.5 3 3.3.5-2.4 2.3.6 3.2L8 10l-3 1.5.6-3.2L3.2 6l3.3-.5L8 2.5Z" />
    </BaseIcon>
  );
}

export function MailIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect height="9" rx="1.2" width="12" x="2" y="3.5" />
      <path d="m2.8 4.5 5.2 4.1 5.2-4.1" />
    </BaseIcon>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect height="6.5" rx="1.1" width="9" x="3.5" y="7" />
      <path d="M5.5 7V5.8a2.5 2.5 0 1 1 5 0V7" />
    </BaseIcon>
  );
}

export function GlobeIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M2.5 8h11" />
      <path d="M8 2.5c1.4 1.5 2.2 3.5 2.2 5.5S9.4 12 8 13.5C6.6 12 5.8 10 5.8 8s.8-4 2.2-5.5Z" />
    </BaseIcon>
  );
}

export function LogoutIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M6 3H3.5v10H6" />
      <path d="M9 5.5 12 8l-3 2.5" />
      <path d="M12 8H5.5" />
    </BaseIcon>
  );
}
