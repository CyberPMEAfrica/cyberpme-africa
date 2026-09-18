const LOGO_SRC = "/brand/cyberpme-africa-logo-v1.png";

export default function BrandLogo({ className = "", compact = false }) {
  const classes = ["brand-logo", compact ? "brand-logo--compact" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <img
      className={classes}
      src={LOGO_SRC}
      alt="CyberPME Africa"
      width="543"
      height="181"
      decoding="async"
    />
  );
}
