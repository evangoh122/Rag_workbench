export default function Presentation() {
  return (
    <div className="w-full aspect-[16/9] min-h-[300px] md:min-h-[500px] bg-surface/10 relative">
      <iframe
        src="https://docs.google.com/presentation/d/1X0Bh06yYY2zbRe7yh7f0itSyiwb0ubVe/embed?start=false&loop=false&delayms=3000"
        className="absolute inset-0 w-full h-full border-0"
        allowFullScreen
        loading="lazy"
        title="Show Your Work Presentation"
      />
    </div>
  );
}
