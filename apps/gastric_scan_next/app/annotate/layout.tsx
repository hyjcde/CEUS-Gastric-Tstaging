export default function AnnotateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-screen w-screen overflow-hidden bg-[#0a0a0a] text-gray-100">
      {children}
    </div>
  );
}
