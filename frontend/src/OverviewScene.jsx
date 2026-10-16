export default function OverviewScene() {
  return <div className="overview-scene" aria-hidden="true">
    <div className="scene-orbit orbit-one"/><div className="scene-orbit orbit-two"/><div className="scene-platform"/>
    <svg className="scene-shield" viewBox="0 0 180 200" fill="none">
      <defs><linearGradient id="shield-face" x1="30" y1="20" x2="150" y2="180" gradientUnits="userSpaceOnUse"><stop stopColor="#2de0a7" stopOpacity=".35"/><stop offset="1" stopColor="#0a7465" stopOpacity=".1"/></linearGradient><linearGradient id="shield-edge" x1="20" y1="30" x2="150" y2="175" gradientUnits="userSpaceOnUse"><stop stopColor="#a6ffe1"/><stop offset=".5" stopColor="#2de0a7"/><stop offset="1" stopColor="#087b68"/></linearGradient></defs>
      <path d="m90 13 64 25v52c0 43-27 75-64 96-37-21-64-53-64-96V38z" fill="url(#shield-face)" stroke="url(#shield-edge)" strokeWidth="2"/>
      <path d="m90 29 50 19v42c0 34-19 62-50 81-31-19-50-47-50-81V48z" stroke="#2de0a7" strokeOpacity=".25"/>
      <path d="m65 96 18 18 34-39" stroke="#70f7ca" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="90" cy="13" r="4" fill="#b7ffe8"/>
    </svg>
    <span className="scene-node node-one"/><span className="scene-node node-two"/><span className="scene-node node-three"/>
  </div>;
}
