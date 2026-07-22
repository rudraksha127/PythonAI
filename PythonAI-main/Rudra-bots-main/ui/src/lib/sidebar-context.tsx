import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface SidebarContextType {
  visible: boolean;
  toggle: () => void;
  show: () => void;
  hide: () => void;
}

const SidebarContext = createContext<SidebarContextType>({
  visible: true,
  toggle: () => {},
  show: () => {},
  hide: () => {},
});

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [visible, setVisible] = useState(true);

  const toggle = useCallback(() => setVisible((v) => !v), []);
  const show = useCallback(() => setVisible(true), []);
  const hide = useCallback(() => setVisible(false), []);

  return (
    <SidebarContext.Provider value={{ visible, toggle, show, hide }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarContext);
}
