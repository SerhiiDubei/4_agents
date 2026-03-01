import React from 'react';
export const CRTOverlay: React.FC = () => {
  return (
    <>
      <div className="crt-overlay pointer-events-none fixed inset-0 z-50 mix-blend-overlay opacity-30"></div>
      <div className="flicker pointer-events-none fixed inset-0 z-40 mix-blend-overlay"></div>
      <div className="pointer-events-none fixed inset-0 z-30 shadow-[inset_0_0_150px_rgba(0,0,0,0.9)]"></div>
    </>);

};