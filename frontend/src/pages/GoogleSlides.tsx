import { Presentation } from 'lucide-react';

export default function GoogleSlides() {
  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto">
      <header className="px-8 py-5 border-b border-[#202532] bg-[#0f1219]/50 backdrop-blur-sm flex-shrink-0">
        <h1 className="text-xl font-semibold text-white flex items-center gap-3">
          <Presentation className="text-pink-400" />
          Presentation
        </h1>
        <p className="text-sm text-gray-400 mt-1">
          Embedded Google Slides deck — RAG Workbench overview
        </p>
      </header>
      <div className="flex-1 p-8 flex items-center justify-center">
        <iframe
          src="https://docs.google.com/presentation/d/1P8DXVd4bkrs0c5r8TXNrPleH7EgB4B9bntZ8O4B7R7w/embed"
          className="w-full h-full max-w-5xl rounded-2xl border border-[#202532] shadow-2xl"
          allowFullScreen
        />
      </div>
    </div>
  );
}
