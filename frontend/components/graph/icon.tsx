import type { ButtonHTMLAttributes } from "react";

const paths = {
  inspect: (
    <>
      <circle cx="10" cy="10" r="6" />
      <path d="m15 15 5 5" />
    </>
  ),
  branch: (
    <>
      <path d="M6 20V4m0 10h7a5 5 0 0 0 5-5V4m-3 3 3-3 3 3" />
    </>
  ),
  mask: (
    <>
      <path strokeDasharray="3 3" d="M4 4h16v16H4z" />
      <path d="m9 15 6-6" />
    </>
  ),
  mesh: (
    <>
      <path d="m12 2 9 5v10l-9 5-9-5V7zm0 10 9-5M12 12 3 7m9 5v10" />
    </>
  ),
  image: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8" cy="8" r="1" />
      <path d="m3 17 6-6 4 4 3-3 5 5" />
    </>
  ),
  background: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 12h9V3M12 21v-9h9" />
      <path fill="currentColor" stroke="none" d="M4 4h7v7H4zm9 9h7v7h-7z" />
    </>
  ),
  more: (
    <>
      <circle cx="5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
    </>
  ),
};

export function Icon({ name }: { name: keyof typeof paths }) {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

export function IconButton({
  icon,
  label,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: keyof typeof paths;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`nodrag icon-button ${className}`}
      {...props}
    >
      <Icon name={icon} />
    </button>
  );
}
