import { alpha, createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#365CCF", dark: "#2846A6", light: "#E9EEFF" },
    success: { main: "#16845B" },
    warning: { main: "#C4740A" },
    error: { main: "#C83F49" },
    background: { default: "#F4F6FA", paper: "#FFFFFF" },
    text: { primary: "#172033", secondary: "#647087" },
    divider: "#E2E6EF",
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", "Microsoft YaHei UI", sans-serif',
    h4: { fontWeight: 720, fontSize: "1.55rem", letterSpacing: "-0.02em" },
    h5: { fontWeight: 720, fontSize: "1.35rem", letterSpacing: "-0.015em" },
    h6: { fontWeight: 700 },
    button: { textTransform: "none", fontWeight: 650 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { minHeight: 34, borderRadius: 8 } } },
    MuiCard: { styleOverrides: { root: { border: "1px solid #E2E6EF", boxShadow: "0 2px 8px rgba(23,32,51,.03)" } } },
    MuiCardContent: { styleOverrides: { root: { padding: 18, "&:last-child": { paddingBottom: 18 } } } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    MuiTableCell: { styleOverrides: { root: { padding: "9px 12px" }, head: { color: "#647087", fontWeight: 700, background: "#F8F9FC" } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 650 } } },
    MuiListItemButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: 10,
          "&.Mui-selected": { background: alpha(theme.palette.primary.main, 0.1), color: theme.palette.primary.main },
        }),
      },
    },
  },
});
