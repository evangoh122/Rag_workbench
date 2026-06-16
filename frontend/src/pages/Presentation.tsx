export default function Presentation() {
  return (
    <div className="w-full aspect-[16/9] min-h-[300px] md:min-h-[500px] bg-surface/10 relative">
      <iframe
        src="https://docs.google.com/presentation/d/13ziiVDNATFpEPlh-tU24JFdmzaYr1qGe/embed?start=false&loop=false&delayms=3000"
        className="absolute inset-0 w-full h-full border-0"
        allowFullScreen
        loading="lazy"
        title="Show Your Work Presentation"
      />
    </div>
  );
}
