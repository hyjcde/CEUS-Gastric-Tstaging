export default function ReaderLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen w-screen overflow-hidden bg-[#08090a] text-gray-100">
      {children}
    </div>
  );
}
