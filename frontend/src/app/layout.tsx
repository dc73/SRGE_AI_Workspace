import type { ReactElement } from "react";

export default function RootLayout({ children }: { children: ReactElement }): ReactElement {
  return (
    <html lang="en">
      <body style={{ fontFamily: "ui-sans-serif, system-ui", margin: 0 }}>
        {children}
      </body>
    </html>
  );
}
