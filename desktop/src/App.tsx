import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  InputLabel,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  BugReportRounded,
  CableRounded,
  DashboardRounded,
  DeveloperBoardRounded,
  FolderOpenRounded,
  GitHub as GitHubIcon,
  InfoOutlineRounded,
  MemoryRounded,
  OpenInNewRounded,
  PlayArrowRounded,
  RefreshRounded,
  SaveAltRounded,
  SettingsRounded,
  StopRounded,
  TuneRounded,
  UsbRounded,
  WarningAmberRounded,
  ExpandMoreRounded,
} from "@mui/icons-material";
import packageInfo from "../package.json";
import { bridgeRequest, onBridgeEvent, openExternal, pickDirectory, pickFile, previewMode, revealPath, type AdapterInfo } from "./api";
import type {
  AutoScanResult,
  BridgeEvent,
  EsiDevice,
  OperationProgress,
  PdoEntry,
  RegisterDefinition,
  SlaveInfo,
  WorkbenchStatus,
} from "./types";
import { hex, stateLabel } from "./types";

type PageKey = "overview" | "registers" | "eeprom";
type Run = <T>(operation: () => Promise<T>, success?: string) => Promise<T | undefined>;
const PREFERRED_ADAPTER_KEY = "ethercat-workbench.preferred-adapter";
const PROJECT_URL = "https://github.com/LINLin190/EtherCAT-Workbench";
const ISSUES_URL = `${PROJECT_URL}/issues`;

interface SlaveContextMenu {
  mouseX: number;
  mouseY: number;
  position: number;
}

const pages: { key: PageKey; label: string; icon: ReactNode }[] = [
  { key: "overview", label: "概览", icon: <DashboardRounded /> },
  { key: "registers", label: "寄存器", icon: <TuneRounded /> },
  { key: "eeprom", label: "EEPROM", icon: <MemoryRounded /> },
];

const cardSx = { borderRadius: 1.25, minWidth: 0 };

function PageTitle({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" gap={2} sx={{ mb: 2 }}>
      <Box>
        <Typography variant="h5" fontWeight={750}>{title}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.35 }}>{subtitle}</Typography>
      </Box>
      {actions && <Stack direction="row" gap={1}>{actions}</Stack>}
    </Stack>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <Card sx={cardSx}>
      <CardContent sx={{ minHeight: 190, display: "grid", placeItems: "center", textAlign: "center" }}>
        <Stack alignItems="center" spacing={1.2} color="text.secondary">
          <DeveloperBoardRounded sx={{ fontSize: 44, opacity: 0.45 }} />
          <Typography>{text}</Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}

function StateChip({ state }: { state: number }) {
  const color = state === 8 ? "success" : state === 0 ? "default" : state === 1 ? "warning" : "primary";
  return <Chip size="small" color={color} variant={state === 8 ? "filled" : "outlined"} label={stateLabel(state)} />;
}

function OverviewPage({ slave, slaves, run, refresh }: { slave?: SlaveInfo; slaves: SlaveInfo[]; run: Run; refresh: () => Promise<void> }) {
  const requestState = (state: number) => run(async () => {
    const value = await bridgeRequest<SlaveInfo[]>("request_state", { position: slave?.position ?? 0, state });
    await refresh();
    return value;
  }, `已请求 ${stateLabel(state)}`);
  const repair = (method: "reconfig" | "recover", success: string) => slave && run(async () => {
    const value = await bridgeRequest(method, { position: slave.position });
    await refresh();
    return value;
  }, success);
  const allOp = slaves.length > 0 && slaves.every((item) => item.state === 8);
  return (
    <>
      <PageTitle title="设备概览" subtitle={slave ? `从站 ${slave.position} · ${slave.name}` : "总线状态与设备信息"} actions={<Button startIcon={<RefreshRounded />} onClick={() => run(refresh)}>刷新状态</Button>} />
      {!slave ? <EmptyState text="连接并扫描后，在左侧选择一个从站" /> : (
        <Stack spacing={1.5}>
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(175px, 1fr))", gap: 1.5 }}>
            {[
              ["当前状态", <StateChip state={slave.state} />],
              ["输入 / 输出", `${slave.input_size} B / ${slave.output_size} B`],
              ["ESC", slave.chip_model],
              ["寄存器族", slave.register_family],
              ["Vendor ID", hex(slave.identity.vendor_id, 8)],
              ["Product Code", hex(slave.identity.product_code, 8)],
              ["Revision", hex(slave.identity.revision, 8)],
              ["Serial Number", hex(slave.identity.serial_number, 8)],
              ["配置地址", slave.configured_address === undefined ? "—" : hex(slave.configured_address)],
              ["AL 状态码", hex(slave.al_status)],
            ].map(([label, value]) => <Card sx={cardSx} key={String(label)}><CardContent sx={{ p: "16px !important" }}><Typography variant="caption" color="text.secondary">{label}</Typography><Box sx={{ mt: 0.7, fontWeight: 700, fontSize: 16 }}>{value}</Box></CardContent></Card>)}
          </Box>
          <Card sx={cardSx}>
            <CardContent>
              <Typography variant="h6" gutterBottom>状态控制</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>状态请求由后台串行执行，并在完成后重新读取总线状态。</Typography>
              <Stack direction="row" gap={1} flexWrap="wrap">
                {[1, 2, 4, 8].map((state) => <Button key={state} variant={slave.state === state ? "contained" : "outlined"} onClick={() => requestState(state)}>{stateLabel(state)}</Button>)}
                <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
                <Button color="warning" onClick={() => repair("reconfig", "重配置完成")}>重配置</Button>
                <Button color="warning" onClick={() => repair("recover", "恢复完成")}>故障恢复</Button>
              </Stack>
            </CardContent>
          </Card>
          <Alert severity={allOp ? "success" : "info"}>{allOp ? "全部从站处于 OP，总线已就绪。" : `已发现 ${slaves.length} 个从站；可在概览中逐站控制状态。`}</Alert>
        </Stack>
      )}
    </>
  );
}

function CoePage({ slave, run }: { slave?: SlaveInfo; run: Run }) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [index, setIndex] = useState("0x1000");
  const [subindex, setSubindex] = useState("0");
  const [data, setData] = useState("");
  const load = () => slave && run(() => bridgeRequest<Record<string, unknown>[]>("object_dictionary", { position: slave.position }).then((value) => { setRows(value); return value; }));
  useEffect(() => { setRows([]); }, [slave?.position]);
  if (!slave) return <><PageTitle title="CoE 对象" subtitle="在线对象字典与 SDO 访问" /><EmptyState text="请先选择从站" /></>;
  return (
    <>
      <PageTitle title="CoE 对象" subtitle={`从站 ${slave.position} · 在线对象字典与 SDO`} actions={<Button variant="contained" onClick={load}>读取对象字典</Button>} />
      <Stack spacing={2}>
        <Card sx={cardSx}><CardContent>
          <Typography variant="h6">快速 SDO 访问</Typography>
          <Stack direction="row" gap={1.2} sx={{ mt: 2 }} alignItems="center">
            <TextField label="Index" value={index} onChange={(e) => setIndex(e.target.value)} size="small" sx={{ width: 150 }} inputProps={{ className: "mono" }} />
            <TextField label="SubIndex" value={subindex} onChange={(e) => setSubindex(e.target.value)} size="small" sx={{ width: 130 }} inputProps={{ className: "mono" }} />
            <TextField label="HEX 数据（写入）" value={data} onChange={(e) => setData(e.target.value)} size="small" fullWidth inputProps={{ className: "mono" }} />
            <Button variant="outlined" onClick={() => run(() => bridgeRequest<{ data: string }>("sdo_read", { position: slave.position, index: Number(index), subindex: Number(subindex) }).then((value) => { setData(value.data); return value; }), "读取完成")}>读取</Button>
            <Button variant="contained" disabled={!data.trim()} onClick={() => run(() => bridgeRequest("sdo_write", { position: slave.position, index: Number(index), subindex: Number(subindex), data }), "写入并回读验证完成")}>写入并验证</Button>
          </Stack>
        </CardContent></Card>
        <Card sx={cardSx}><TableContainer sx={{ maxHeight: "calc(100vh - 390px)" }}><Table stickyHeader size="small"><TableHead><TableRow>{["Index", "Sub", "名称", "类型", "位宽", "访问", "来源"].map((h) => <TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead><TableBody>
          {rows.map((row, i) => <TableRow hover key={i}><TableCell className="mono">{hex(Number(row.index))}</TableCell><TableCell>{String(row.subindex)}</TableCell><TableCell>{String(row.name)}</TableCell><TableCell>{String(row.data_type)}</TableCell><TableCell>{String(row.bit_length)}</TableCell><TableCell>{String(row.access)}</TableCell><TableCell>{String(row.source)}</TableCell></TableRow>)}
          {!rows.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 8, color: "text.secondary" }}>点击“读取对象字典”开始</TableCell></TableRow>}
        </TableBody></Table></TableContainer></Card>
      </Stack>
    </>
  );
}

function PdoPage({ slave, run }: { slave?: SlaveInfo; run: Run }) {
  const [mapping, setMapping] = useState<{ rx: PdoEntry[]; tx: PdoEntry[] }>({ rx: [], tx: [] });
  const [tab, setTab] = useState(0);
  useEffect(() => { setMapping({ rx: [], tx: [] }); }, [slave?.position]);
  const load = () => slave && run(() => bridgeRequest<{ rx: PdoEntry[]; tx: PdoEntry[] }>("pdo_mapping", { position: slave.position }).then((value) => { setMapping(value); return value; }));
  const rows = tab === 0 ? mapping.tx : mapping.rx;
  if (!slave) return <><PageTitle title="PDO 映射" subtitle="过程数据布局" /><EmptyState text="请先选择从站" /></>;
  return <><PageTitle title="PDO 映射" subtitle={`从站 ${slave.position} · 位偏移和数据类型`} actions={<Button variant="contained" onClick={load}>读取映射</Button>} />
    <Card sx={cardSx}><Tabs value={tab} onChange={(_, value) => setTab(value)} sx={{ px: 2 }}><Tab label={`输入 TxPDO (${mapping.tx.length})`} /><Tab label={`输出 RxPDO (${mapping.rx.length})`} /></Tabs><Divider />
      <TableContainer sx={{ maxHeight: "calc(100vh - 290px)" }}><Table stickyHeader size="small"><TableHead><TableRow>{["PDO", "对象", "Sub", "名称", "类型", "位长度", "位偏移"].map((h) => <TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead><TableBody>{rows.map((row, i) => <TableRow hover key={i}><TableCell className="mono">{hex(row.pdo_index)}</TableCell><TableCell className="mono">{hex(row.index)}</TableCell><TableCell>{row.subindex}</TableCell><TableCell>{row.name || "—"}</TableCell><TableCell>{row.data_type || "—"}</TableCell><TableCell>{row.bit_length}</TableCell><TableCell>{row.bit_offset}</TableCell></TableRow>)}{!rows.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 10, color: "text.secondary" }}>尚未读取映射</TableCell></TableRow>}</TableBody></Table></TableContainer>
    </Card></>;
}

interface Snapshot { inputs: string[]; outputs: string[]; actual_wkc: number; expected_wkc: number; cycle_count: number; timeout_count: number; wkc_error_count: number; consecutive_errors: number }
function IoPage({ slave, status, snapshot, run, refresh }: { slave?: SlaveInfo; status: WorkbenchStatus; snapshot?: Snapshot; run: Run; refresh: () => void }) {
  const [period, setPeriod] = useState("1");
  const [output, setOutput] = useState("");
  const toggle = () => run(() => bridgeRequest(status.cycle_running ? "stop_cycle" : "start_cycle", status.cycle_running ? {} : { period_ms: Number(period) }).then((result) => { refresh(); return result; }), status.cycle_running ? "周期通信已安全停止" : "周期通信已启动");
  return <><PageTitle title="在线 I/O" subtitle="周期通信、WKC 健康度与过程数据" actions={<><FormControl size="small" sx={{ width: 126 }}><InputLabel>周期</InputLabel><Select label="周期" value={period} disabled={status.cycle_running} onChange={(e) => setPeriod(e.target.value)}>{["0.5", "1", "2", "5", "10", "20"].map((p) => <MenuItem value={p} key={p}>{p} ms</MenuItem>)}</Select></FormControl><Button color={status.cycle_running ? "error" : "primary"} variant="contained" disabled={!status.connected || !status.slaves.length} startIcon={status.cycle_running ? <StopRounded /> : <PlayArrowRounded />} onClick={toggle}>{status.cycle_running ? "安全停止" : "启动周期"}</Button></>} />
    <Box sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 2, mb: 2 }}>{[["WKC", snapshot ? `${snapshot.actual_wkc} / ${snapshot.expected_wkc}` : "—"], ["周期计数", snapshot?.cycle_count ?? "—"], ["WKC 错误", snapshot?.wkc_error_count ?? "—"], ["超时", snapshot?.timeout_count ?? "—"]].map(([label, value]) => <Card sx={cardSx} key={String(label)}><CardContent><Typography color="text.secondary" variant="caption">{label}</Typography><Typography variant="h6" className="mono" sx={{ mt: 0.8 }}>{value}</Typography></CardContent></Card>)}</Box>
    {!slave ? <EmptyState text="选择从站后查看其过程数据" /> : <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 2 }}>
      <Card sx={cardSx}><CardContent><Typography variant="h6">输入数据</Typography><Typography className="mono" sx={{ mt: 2, p: 2, bgcolor: "#F7F8FB", borderRadius: 2, minHeight: 82 }}>{snapshot?.inputs?.[slave.position - 1] || "尚无周期数据"}</Typography></CardContent></Card>
      <Card sx={cardSx}><CardContent><Typography variant="h6">输出数据</Typography><Stack direction="row" gap={1} sx={{ mt: 2 }}><TextField fullWidth size="small" label={`HEX · ${slave.output_size} B`} value={output} onChange={(e) => setOutput(e.target.value)} inputProps={{ className: "mono" }} /><Button variant="contained" disabled={!status.cycle_running || !slave.output_size || !output.trim()} onClick={() => run(() => bridgeRequest("set_output", { position: slave.position, data: output }), "输出已应用")}>应用</Button></Stack><Typography variant="caption" color="text.secondary">仅在周期运行时可写；后台确认成功后才更新状态。</Typography></CardContent></Card>
    </Box>}</>;
}

interface RegisterValue { position: number; address: number; data: string; wkc: number; duration_ms: number; timestamp: number }
interface RegisterWriteContext { address: number; width: number; name: string; access: string; known: boolean }

const registerKey = (address: number, width: number) => `${address}:${width}`;

/** Accepts "0x0130" and "0130"; plain digits are hexadecimal, not decimal. */
function parseHexInput(text: string): number | undefined {
  const cleaned = text.trim().replace(/^0x/i, "");
  if (!/^[0-9A-Fa-f]+$/.test(cleaned)) return undefined;
  const value = parseInt(cleaned, 16);
  return Number.isNaN(value) ? undefined : value;
}

function littleEndianValue(data: string): bigint {
  return data.trim().split(/\s+/).filter(Boolean).reduceRight((value, byte) => (value << 8n) | BigInt(`0x${byte}`), 0n);
}

function RegistersPage({ slave, run }: { slave?: SlaveInfo; run: Run }) {
  const [catalog, setCatalog] = useState<RegisterDefinition[]>([]);
  const [selected, setSelected] = useState<RegisterDefinition>();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<RegisterValue>();
  const [pinned, setPinned] = useState<RegisterDefinition[]>([]);
  const [watchValues, setWatchValues] = useState<Record<string, RegisterValue>>({});
  const [watching, setWatching] = useState(false);
  const [watchError, setWatchError] = useState("");
  const [intervalMs, setIntervalMs] = useState(1000);
  const [writeOpen, setWriteOpen] = useState(false);
  const [writeContext, setWriteContext] = useState<RegisterWriteContext>();
  const [writeData, setWriteData] = useState("");
  const [plan, setPlan] = useState<{ plan_id: string; plan: Record<string, unknown> }>();
  const [resetConfirm, setResetConfirm] = useState(false);
  const [rawAddress, setRawAddress] = useState("0x0000");
  const [rawSize, setRawSize] = useState(1);
  const [rawResult, setRawResult] = useState<RegisterValue>();
  const [rawAccess, setRawAccess] = useState("RW");
  const watchInFlight = useRef(false);

  useEffect(() => { bridgeRequest<RegisterDefinition[]>("register_catalog").then(setCatalog); }, []);
  useEffect(() => {
    setSelected(undefined); setResult(undefined); setPinned([]); setWatchValues({}); setWatching(false);
    setWatchError(""); setPlan(undefined); setWriteOpen(false); setResetConfirm(false); setRawResult(undefined);
  }, [slave?.position]);

  const filtered = catalog.filter((definition) =>
    `${definition.name} ${definition.group} ${definition.description} ${hex(definition.address)}`
      .toLowerCase().includes(query.toLowerCase()),
  );
  const read = async (definition: RegisterDefinition) => {
    setSelected(definition);
    if (!slave) return;
    await run(() => bridgeRequest<RegisterValue>("register_read", {
      position: slave.position, address: definition.address, size: definition.width ?? definition.size,
    }).then((value) => { setResult(value); return value; }));
  };
  const readRaw = async () => {
    if (!slave) return;
    const address = parseHexInput(rawAddress);
    if (address === undefined) return;
    await run(() => bridgeRequest<RegisterValue>("register_read", {
      position: slave.position, address, size: rawSize,
    }).then((value) => { setRawResult(value); return value; }), "原始寄存器读取完成");
  };

  useEffect(() => {
    if (!watching || !pinned.length || !slave) return;
    let active = true;
    const poll = async () => {
      if (watchInFlight.current) return;
      watchInFlight.current = true;
      try {
        const values = await bridgeRequest<RegisterValue[]>("register_watch", {
          position: slave.position,
          requests: pinned.map((definition) => ({ address: definition.address, size: definition.width ?? definition.size })),
        });
        if (active) {
          setWatchValues(Object.fromEntries(values.map((value) => [registerKey(value.address, value.data.split(/\s+/).length), value])));
          setWatchError("");
        }
      } catch (error) {
        if (active) { setWatching(false); setWatchError(error instanceof Error ? error.message : String(error)); }
      } finally { watchInFlight.current = false; }
    };
    void poll();
    const timer = window.setInterval(poll, intervalMs);
    return () => { active = false; window.clearInterval(timer); };
  }, [watching, pinned, slave, intervalMs]);

  const togglePinned = (definition: RegisterDefinition) => {
    const width = definition.width ?? definition.size ?? 1;
    const exists = pinned.some((item) => item.address === definition.address && (item.width ?? item.size) === width);
    setPinned((items) => exists
      ? items.filter((item) => !(item.address === definition.address && (item.width ?? item.size) === width))
      : [...items, definition]);
    if (exists && pinned.length === 1) setWatching(false);
  };
  const removePinned = (definition: RegisterDefinition) => {
    const width = definition.width ?? definition.size ?? 1;
    setPinned((items) => items.filter((item) => !(item.address === definition.address && (item.width ?? item.size) === width)));
    if (pinned.length === 1) setWatching(false);
  };
  const openWrite = (context: RegisterWriteContext) => {
    setWriteContext(context); setWriteData(""); setPlan(undefined); setWriteOpen(true);
  };
  const prepareWrite = async () => {
    if (!slave || !writeContext) return;
    const value = await run(() => bridgeRequest<{ plan_id: string; plan: Record<string, unknown> }>(
      "register_prepare_write",
      { position: slave.position, address: writeContext.address, data: writeData, semantics: writeContext.access, known_register: writeContext.known },
    ));
    if (value) setPlan(value);
  };
  const executeWrite = async () => {
    if (!plan) return;
    const value = await run(() => bridgeRequest("register_execute_write", { plan_id: plan.plan_id }), "寄存器写入并验证完成");
    if (value) {
      setPlan(undefined); setWriteOpen(false);
      if (writeContext?.known && selected) await read(selected); else await readRaw();
    }
  };
  const decodedFields = useMemo(() => {
    if (!selected?.bit_fields || !result?.data) return [];
    const value = littleEndianValue(result.data);
    return selected.bit_fields.map((field) => ({
      name: field.name,
      value: (value >> BigInt(field.shift)) & ((1n << BigInt(field.bits)) - 1n),
    }));
  }, [selected, result]);

  return <><PageTitle title="寄存器" subtitle={slave ? `从站 ${slave.position} · ${slave.chip_model} · ${slave.register_family}` : "标准 ESC 寄存器读取与诊断"} />
    {!slave ? <EmptyState text="请先选择从站" /> : <Stack spacing={1.5}>
      <Alert severity="info">目标：从站 {slave.position} · 配置地址 {slave.configured_address === undefined ? "未知" : hex(slave.configured_address)} · 默认只读；所有写入均记录 AUDIT。</Alert>
      <Box sx={{ display: "grid", gridTemplateColumns: "minmax(340px, 0.85fr) minmax(0, 1.15fr)", gap: 1.5, minHeight: 0 }}>
        <Card sx={cardSx}><CardContent sx={{ pb: "14px !important" }}><TextField fullWidth size="small" placeholder="搜索名称、地址或分组" value={query} onChange={(e) => setQuery(e.target.value)} /></CardContent><Divider /><List dense sx={{ overflow: "auto", maxHeight: "calc(100vh - 330px)", p: 0.8 }}>{filtered.map((definition) => <ListItemButton selected={selected?.address === definition.address} key={`${definition.address}-${definition.name}`} onClick={() => void read(definition)}><ListItemText primary={definition.name} secondary={`${hex(definition.address)} · ${definition.group}`} /><Chip size="small" variant="outlined" label={definition.access} /></ListItemButton>)}</List></Card>
        <Card sx={cardSx}><CardContent>{selected ? <Stack spacing={2}><Stack direction="row" justifyContent="space-between"><Box><Typography variant="h6">{selected.name}</Typography><Typography color="text.secondary">{selected.description}</Typography></Box><Chip label={selected.access} size="small" /></Stack><Divider /><Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 2 }}><Box><Typography variant="caption" color="text.secondary">地址</Typography><Typography className="mono">{hex(selected.address)}</Typography></Box><Box><Typography variant="caption" color="text.secondary">宽度</Typography><Typography>{selected.width ?? selected.size} byte</Typography></Box><Box><Typography variant="caption" color="text.secondary">WKC</Typography><Typography>{result ? result.wkc : "—"}</Typography></Box></Box><Box><Typography variant="caption" color="text.secondary">读取值</Typography><Typography className="mono" sx={{ mt: 1, p: 2, borderRadius: 2, bgcolor: "#F6F8FC", fontSize: 22 }}>{result?.data ?? "选择即读取"}</Typography></Box>{decodedFields.length > 0 && <Box><Typography variant="caption" color="text.secondary">位字段</Typography><Stack direction="row" gap={0.7} flexWrap="wrap" sx={{ mt: 0.8 }}>{decodedFields.map((field) => <Chip key={field.name} size="small" label={`${field.name}: ${field.value}`} />)}</Stack></Box>}<Stack direction="row" gap={1} alignItems="center"><Button variant={pinned.some((item) => item.address === selected.address) ? "contained" : "outlined"} onClick={() => togglePinned(selected)}>{pinned.some((item) => item.address === selected.address) ? "取消固定" : "固定监视"}</Button>{selected.address === 0x0040 ? <Button color="error" onClick={() => setResetConfirm(true)}>发送三帧 RES</Button> : selected.access !== "RO" && <Button color="warning" onClick={() => openWrite({ address: selected.address, width: selected.width ?? selected.size ?? 1, name: selected.name, access: selected.access, known: true })}>进入写入模式</Button>}</Stack><Alert severity={selected.access === "RO" ? "info" : "warning"}>{selected.access === "RO" ? "只读寄存器，不提供写入操作。" : selected.address === 0x0040 ? "复位只允许以三个连续、独立 FPWR 发送 52、45、53。" : `${selected.access} 写入严格使用定义宽度，并在第二次确认后执行。`}</Alert></Stack> : <Box sx={{ minHeight: 300, display: "grid", placeItems: "center", color: "text.secondary" }}>从左侧选择寄存器即可读取</Box>}</CardContent></Card>
      </Box>
      <Card sx={cardSx}><CardContent><Stack direction="row" justifyContent="space-between" alignItems="center"><Box><Typography variant="h6">固定监视</Typography><Typography variant="body2" color="text.secondary">合并相邻范围；同一时刻最多一个请求在途，失败后自动暂停。</Typography></Box><Stack direction="row" gap={1}><FormControl size="small" sx={{ width: 130 }}><InputLabel>刷新周期</InputLabel><Select label="刷新周期" value={intervalMs} disabled={watching} onChange={(e) => setIntervalMs(Number(e.target.value))}>{[500, 1000, 2000, 5000].map((value) => <MenuItem value={value} key={value}>{value} ms</MenuItem>)}</Select></FormControl><Button disabled={!pinned.length} variant={watching ? "contained" : "outlined"} onClick={() => setWatching(!watching)}>{watching ? "暂停" : "开始"}</Button><Button disabled={!pinned.length} onClick={() => { setPinned([]); setWatchValues({}); setWatching(false); }}>清空</Button></Stack></Stack>{watchError && <Alert severity="error" sx={{ mt: 1.5 }}>{watchError}</Alert>}<TableContainer sx={{ mt: 1.5 }}><Table size="small"><TableHead><TableRow>{["地址", "名称", "值", "WKC", "耗时", "操作"].map((item) => <TableCell key={item}>{item}</TableCell>)}</TableRow></TableHead><TableBody>{pinned.map((definition) => { const width = definition.width ?? definition.size ?? 1; const value = watchValues[registerKey(definition.address, width)]; return <TableRow key={registerKey(definition.address, width)}><TableCell className="mono">{hex(definition.address)}</TableCell><TableCell>{definition.name}</TableCell><TableCell className="mono">{value?.data ?? "—"}</TableCell><TableCell>{value?.wkc ?? "—"}</TableCell><TableCell>{value ? `${value.duration_ms.toFixed(2)} ms` : "—"}</TableCell><TableCell><Button size="small" onClick={() => removePinned(definition)}>移除</Button></TableCell></TableRow>; })}{!pinned.length && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: "text.secondary" }}>从标准寄存器详情中固定需要监视的项目</TableCell></TableRow>}</TableBody></Table></TableContainer></CardContent></Card>
        <Accordion disableGutters><AccordionSummary expandIcon={<ExpandMoreRounded />}><Box><Typography fontWeight={700}>原始地址工具</Typography><Typography variant="caption" color="text.secondary">用于未收录地址；写入不会假定寄存器语义，请对照数据手册。</Typography></Box></AccordionSummary><AccordionDetails><Alert severity="warning" sx={{ mb: 1.5 }}>未知地址写入可能破坏链路、状态机或 EEPROM 控制状态，仍会生成计划、二次确认并记录 AUDIT。</Alert><Stack direction="row" gap={1} alignItems="center" flexWrap="wrap"><TextField size="small" label="地址" value={rawAddress} onChange={(e) => setRawAddress(e.target.value)} inputProps={{ className: "mono" }} sx={{ width: 150 }} /><TextField size="small" type="number" label="宽度" value={rawSize} onChange={(e) => setRawSize(Number(e.target.value))} inputProps={{ min: 1, max: 256 }} sx={{ width: 110 }} /><Button variant="outlined" disabled={parseHexInput(rawAddress) === undefined} onClick={readRaw}>读取</Button><FormControl size="small" sx={{ width: 150 }}><InputLabel>写入语义</InputLabel><Select label="写入语义" value={rawAccess} onChange={(e) => setRawAccess(e.target.value)}>{["RW", "WO", "W1C", "W1S", "WAC", "SELF_CLEARING", "VOLATILE"].map((item) => <MenuItem value={item} key={item}>{item}</MenuItem>)}</Select></FormControl><Button color="warning" disabled={parseHexInput(rawAddress) === undefined} onClick={() => openWrite({ address: parseHexInput(rawAddress) ?? 0, width: rawSize, name: `原始地址 ${rawAddress}`, access: rawAccess, known: false })}>写入工具</Button><Typography className="mono">{rawResult?.data ?? ""}</Typography></Stack></AccordionDetails></Accordion>
    </Stack>}
    <Dialog open={writeOpen} onClose={() => { setWriteOpen(false); setPlan(undefined); }} fullWidth maxWidth="sm"><DialogTitle>寄存器安全写入</DialogTitle><DialogContent><Stack spacing={2} sx={{ pt: 1 }}><Alert severity="warning">目标从站 {slave?.position ?? "—"} · {writeContext?.name} · {hex(writeContext?.address ?? 0)}。请确认访问语义和最终字节。</Alert><TextField label={writeContext?.access === "W1C" || writeContext?.access === "W1S" ? "操作掩码（HEX）" : `目标值（HEX，${writeContext?.known ? `必须 ${writeContext.width} B` : "1–256 B"}）`} value={writeData} onChange={(e) => { setWriteData(e.target.value); setPlan(undefined); }} inputProps={{ className: "mono" }} />{plan && <Box sx={{ p: 2, bgcolor: "#F7F8FB", borderRadius: 2 }}><Typography variant="subtitle2">写入计划</Typography><Typography className="mono">当前值：{String(plan.plan.current || "不可回读")}</Typography><Typography className="mono">目标值：{String(plan.plan.target)}</Typography><Typography className="mono">变化位：{String(plan.plan.changed_mask || "按语义执行")}</Typography></Box>}</Stack></DialogContent><DialogActions><Button onClick={() => { setWriteOpen(false); setPlan(undefined); }}>取消</Button>{!plan ? <Button variant="contained" color="warning" disabled={!writeData.trim()} onClick={prepareWrite}>生成写入计划</Button> : <Button variant="contained" color="error" onClick={executeWrite}>确认并执行</Button>}</DialogActions></Dialog>
    <Dialog open={resetConfirm} onClose={() => setResetConfirm(false)}><DialogTitle>确认复位 EtherCAT 控制器</DialogTitle><DialogContent><Alert severity="error">将独占 Worker，以三个连续、独立 FPWR 向 0x0040 写入 52、45、53；从站会短暂掉线。</Alert></DialogContent><DialogActions><Button onClick={() => setResetConfirm(false)}>取消</Button><Button color="error" variant="contained" onClick={async () => { const value = await run(() => bridgeRequest("register_reset", { position: slave?.position }), "RES 复位序列已发送"); if (value) setResetConfirm(false); }}>确认并发送</Button></DialogActions></Dialog>
  </>;
}

interface EsiResult { document_id: string; path: string; vendor_id: number; vendor_name: string; devices: EsiDevice[] }
interface TargetResult { target_id: string; size: number; sha256: string; supported: string[]; omitted: string[]; device: EsiDevice }
interface ProgressState extends OperationProgress { percent: number; tone?: "error" | "success" | "info" }
interface EepromComparisonResult { equal: boolean; differing_bytes: number; first_difference?: number; target_sha256: string; readback_sha256: string }
interface EepromReadResult { data: string; size: number; sha256: string; read_at: string; sii_valid: boolean; sii_error?: string; identity?: { vendor_id: number; product_code: number; revision: number; serial_number: number }; category_count?: number; categories?: number[]; end_offset?: number; comparison?: EepromComparisonResult }
interface EepromFlashDetails { bytes_read_back: number; words_written: number; comparison: EepromComparisonResult; sii_valid: boolean; semantic_valid: boolean; image_verification: string; reset_sequence?: boolean[]; rediscovered?: boolean; reload_verified?: boolean }
interface EepromFlashPayload { success: boolean; result: EepromFlashDetails; slaves: SlaveInfo[] }
interface EepromOperationResult { title: string; severity: "success" | "warning" | "error"; payload?: EepromFlashPayload; error?: string }

function formatHexView(data: string): string {
  const bytes = data.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 16) {
    lines.push(`${offset.toString(16).toUpperCase().padStart(4, "0")}: ${bytes.slice(offset, offset + 16).join(" ")}`);
  }
  return lines.join("\n");
}

function deviceRevision(device: EsiDevice): number {
  return Number(device.revision ?? device.revision_number ?? 0);
}

function EepromPage({ slave, status, setProgress, run }: { slave?: SlaveInfo; status: WorkbenchStatus; setProgress: (value?: ProgressState) => void; run: Run }) {
  const [esi, setEsi] = useState<EsiResult>();
  const [ordinal, setOrdinal] = useState(0);
  const [target, setTarget] = useState<TargetResult>();
  const [physicalSize, setPhysicalSize] = useState<number>();
  const [capacityError, setCapacityError] = useState("");
  const [generationError, setGenerationError] = useState("");
  const [backupPath, setBackupPath] = useState("");
  const [readResult, setReadResult] = useState<EepromReadResult>();
  const [operationResult, setOperationResult] = useState<EepromOperationResult>();
  const currentDevice = esi?.devices[ordinal];
  const capacityKnown = physicalSize !== undefined && !capacityError;
  const capacityMatches = Boolean(target && capacityKnown && target.size === physicalSize);
  const identityMismatch = Boolean(slave && currentDevice && (
    slave.identity.vendor_id !== esi?.vendor_id || slave.identity.product_code !== currentDevice.product_code ||
    slave.identity.revision !== deviceRevision(currentDevice)
  ));
  const canFlash = Boolean(slave && target && capacityMatches && !status.cycle_running && slave.state === 1);
  const blockers = [!target && "需要选择有效 XML", !capacityKnown && "需要成功读取物理 EEPROM 容量", target && capacityKnown && !capacityMatches && "目标容量与物理 EEPROM 不一致", status.cycle_running && "需要停止周期通信", slave?.state !== 1 && "需要将从站切换到 INIT"].filter(Boolean) as string[];
  useEffect(() => {
    setPhysicalSize(undefined); setCapacityError(""); setReadResult(undefined); setOperationResult(undefined); setBackupPath("");
    if (slave) bridgeRequest<{ size: number }>("eeprom_capacity", { position: slave.position })
      .then((value) => setPhysicalSize(value.size))
      .catch((error) => setCapacityError(error instanceof Error ? error.message : String(error)));
  }, [slave?.position]);

  const generate = useCallback(async (document: EsiResult, selectedOrdinal: number) => {
    setTarget(undefined); setOperationResult(undefined); setGenerationError("");
    const value = await run(async () => {
      try { return await bridgeRequest<TargetResult>("sii_generate", { document_id: document.document_id, ordinal: selectedOrdinal }); }
      catch (error) { setGenerationError(error instanceof Error ? error.message : String(error)); throw error; }
    });
    if (value) setTarget(value);
  }, [run]);

  useEffect(() => {
    if (!slave || !esi) return;
    const matched = esi.devices.findIndex((device) =>
      esi.vendor_id === slave.identity.vendor_id && device.product_code === slave.identity.product_code &&
      deviceRevision(device) === slave.identity.revision,
    );
    if (matched >= 0 && matched !== ordinal) {
      setOrdinal(matched);
      void generate(esi, matched);
    }
  }, [esi, generate, ordinal, slave]);

  const selectXml = async () => {
    const path = await pickFile(["xml"]); if (!path) return;
    const document = await run(() => bridgeRequest<EsiResult>("esi_load", { path }));
    if (document) {
      const matched = slave ? document.devices.findIndex((device) =>
        document.vendor_id === slave.identity.vendor_id && device.product_code === slave.identity.product_code && deviceRevision(device) === slave.identity.revision,
      ) : -1;
      const selectedOrdinal = matched >= 0 ? matched : 0;
      setEsi(document); setOrdinal(selectedOrdinal); await generate(document, selectedOrdinal);
    }
  };
  const changeDevice = async (value: number) => { setOrdinal(value); if (esi) await generate(esi, value); };
  const operation = async <T,>(fn: () => Promise<T>, success: string): Promise<T | undefined> => {
    setOperationResult(undefined);
    setProgress({ operation: "eeprom", stage: "准备", completed: 0, total: 100, percent: 0, detail: "正在检查操作条件", tone: "info" });
    try {
      const value = await fn();
      const flashPayload = value as EepromFlashPayload;
      if (flashPayload && typeof flashPayload === "object" && "success" in flashPayload) {
        if (!flashPayload.success) {
          const title = "镜像校验失败";
          setProgress({ operation: "eeprom", stage: title, completed: 100, total: 100, percent: 100, detail: flashPayload.result.image_verification, tone: "error" });
          setOperationResult({ title, severity: "error", payload: flashPayload });
          return value;
        }
        const reloadFailed = flashPayload.result.reload_verified === false;
        const title = reloadFailed ? "镜像校验成功；复位后复核失败" : success;
        setProgress({ operation: "eeprom", stage: title, completed: 100, total: 100, percent: 100, detail: reloadFailed ? "EEPROM 镜像已通过校验，但复位后的重新加载复核未通过。" : success, tone: reloadFailed ? "info" : "success" });
        setOperationResult({ title, severity: reloadFailed ? "warning" : "success", payload: flashPayload });
      } else {
        setProgress({ operation: "eeprom", stage: success, completed: 100, total: 100, percent: 100, detail: success, tone: "success" });
        setOperationResult({ title: success, severity: "success" });
      }
      return value;
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      setProgress({ operation: "eeprom", stage: "操作失败", completed: 100, total: 100, percent: 100, detail: text, tone: "error" });
      setOperationResult({ title: "操作失败", severity: "error", error: text });
      return undefined;
    }
  };
  const readFull = async () => {
    if (!slave) return;
    const value = await operation(() => bridgeRequest<EepromReadResult>("eeprom_read", { position: slave.position, target_id: target?.target_id }), "完整读取完成");
    if (value) setReadResult(value);
  };
  const backup = async () => { if (!slave) return; const directory = await pickDirectory(); if (directory) { const value = await operation(() => bridgeRequest<{ binary_path: string }>("eeprom_backup", { position: slave.position, directory }), "BIN 备份完成"); if (value) setBackupPath(value.binary_path); } };
  const restore = async () => { if (!slave) return; const path = await pickFile(["bin"]); if (path) await operation(() => bridgeRequest<EepromFlashPayload>("eeprom_restore", { position: slave.position, path, auto_reset: true }), "恢复并校验完成"); };
  const flash = () => slave && target && operation(() => bridgeRequest<EepromFlashPayload>("eeprom_flash", { position: slave.position, target_id: target.target_id, auto_reset: true }), "烧录并校验完成");

  return <><PageTitle title="EEPROM" subtitle="ESI 预览、完整读取、BIN 备份与安全烧录" />
    {!slave ? <EmptyState text="请先选择目标从站" /> : <Stack spacing={1.5}>
      <Box sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1.05fr) minmax(360px, .95fr)", gap: 1.5 }}>
        <Card sx={cardSx}><CardContent><Stack direction="row" alignItems="center" justifyContent="space-between"><Box><Typography variant="h6">烧录目标</Typography><Typography color="text.secondary">XML 或 Device 变化时自动生成</Typography></Box><Button variant="outlined" startIcon={<FolderOpenRounded />} onClick={selectXml}>选择 XML</Button></Stack><Divider sx={{ my: 2 }} />
          {esi ? <Stack spacing={1.5}><TextField label="XML 文件" size="small" value={esi.path} InputProps={{ readOnly: true }} /><FormControl fullWidth size="small"><InputLabel>Device</InputLabel><Select label="Device" value={ordinal} onChange={(e) => changeDevice(Number(e.target.value))}>{esi.devices.map((device, i) => <MenuItem value={i} key={i}>{device.name} · {hex(device.product_code, 8)}</MenuItem>)}</Select></FormControl>{identityMismatch && <Alert severity="warning">当前 XML/Device 身份与目标从站不一致；允许继续生成，但烧录前请确认。</Alert>}{generationError ? <Alert severity="error"><Typography fontWeight={700}>目标生成失败</Typography>{generationError}</Alert> : target ? <Alert severity={target.omitted.length ? "warning" : "success"}>{target.omitted.length ? `目标已生成，并明确省略或降级 ${target.omitted.length} 项；请查看 Smart View。` : "目标已生成，可进入条件检查。"}</Alert> : <Alert severity="info">正在生成 Smart View…</Alert>}</Stack> : <Box sx={{ py: 6, textAlign: "center", color: "text.secondary" }}>选择厂商 ESI XML 后自动解析并生成目标</Box>}
        </CardContent></Card>
        <Card sx={cardSx}><CardContent><Typography variant="h6">Smart View</Typography><Typography color="text.secondary">随当前 XML 和 Device 实时更新</Typography><Divider sx={{ my: 2 }} />
          {currentDevice && target ? <Stack spacing={1.5}><Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>{[["设备", currentDevice.name], ["厂商", esi?.vendor_name], ["Product Code", hex(currentDevice.product_code, 8)], ["Revision", hex(deviceRevision(currentDevice), 8)], ["目标容量", `${target.size} B`], ["物理容量", capacityError ? "读取失败" : physicalSize === undefined ? "读取中…" : `${physicalSize} B`], ["SHA-256", target.sha256]].map(([label, value]) => <Box key={String(label)}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography className={String(label).includes("Code") || label === "SHA-256" ? "mono" : ""} noWrap title={String(value)}>{value}</Typography></Box>)}</Box>{capacityError && <Alert severity="error">{capacityError}</Alert>}<Divider /><Box><Typography variant="subtitle2">已转换内容</Typography><Stack direction="row" flexWrap="wrap" gap={0.7} sx={{ mt: 1 }}>{target.supported.map((item) => <Chip size="small" color="success" variant="outlined" label={item} key={item} />)}</Stack></Box>{target.omitted.length > 0 && <Box><Typography variant="subtitle2" color="warning.main">未转换或容量降级内容</Typography>{target.omitted.map((item) => <Typography variant="body2" color="warning.main" key={item}>• {item}</Typography>)}</Box>}</Stack> : <Box sx={{ py: 6, textAlign: "center", color: "text.secondary" }}>尚无可预览的烧录目标</Box>}
        </CardContent></Card>
      </Box>
      <Card sx={cardSx}><CardContent><Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 3 }}><Box><Typography variant="h6">读取与恢复</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>“完整读取”仅刷新 Smart/Hex View；“备份 BIN”读取后直接保存可恢复文件。读取进度显示在右下角通知中。</Typography><Stack direction="row" gap={1} flexWrap="wrap"><Tooltip title={status.cycle_running ? "完整读取前必须停止周期通信" : ""}><span><Button variant="outlined" disabled={status.cycle_running} onClick={readFull}>完整读取</Button></span></Tooltip><Tooltip title={status.cycle_running ? "备份前必须停止周期通信" : ""}><span><Button variant="outlined" disabled={status.cycle_running} startIcon={<SaveAltRounded />} onClick={backup}>备份 BIN</Button></span></Tooltip><Tooltip title={status.cycle_running || slave.state !== 1 ? "恢复前必须停止周期通信并切换到 INIT" : ""}><span><Button color="warning" variant="outlined" disabled={status.cycle_running || slave.state !== 1} onClick={restore}>从 BIN 恢复</Button></span></Tooltip>{backupPath && <Button onClick={() => revealPath(backupPath)} startIcon={<FolderOpenRounded />}>打开备份位置</Button>}</Stack></Box><Box><Typography variant="h6">烧录条件</Typography><Stack direction="row" gap={0.8} flexWrap="wrap" sx={{ my: 1.5 }}><Chip color={target ? "success" : "default"} label={target ? "目标已生成" : "缺少目标"} /><Chip color={capacityMatches ? "success" : "warning"} label={!capacityKnown ? "容量未知" : capacityMatches ? "容量一致" : "容量不一致"} /><Chip color={!status.cycle_running ? "success" : "warning"} label={!status.cycle_running ? "周期已停止" : "周期运行中"} /><Chip color={slave.state === 1 ? "success" : "warning"} label={slave.state === 1 ? "从站 INIT" : `当前 ${stateLabel(slave.state)}`} /></Stack><Tooltip title={blockers.join("；")}><span><Button variant="contained" color="warning" disabled={!canFlash} startIcon={<MemoryRounded />} onClick={flash}>烧录</Button></span></Tooltip>{blockers.length > 0 && <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>{blockers.join("；")}</Typography>}</Box></Box></CardContent></Card>
      {readResult && <Card sx={cardSx}><CardContent><Typography variant="h6">最近完整读取</Typography><Box sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 1.5, mt: 1.5 }}>{[["读取时间", new Date(readResult.read_at).toLocaleString()], ["容量", `${readResult.size} B`], ["SII 结构", readResult.sii_valid ? `${readResult.category_count ?? 0} 个 Category` : "无效"], ["差异", readResult.comparison ? `${readResult.comparison.differing_bytes} byte` : "未选择目标"], ["Vendor ID", readResult.identity ? hex(readResult.identity.vendor_id, 8) : "—"], ["Product Code", readResult.identity ? hex(readResult.identity.product_code, 8) : "—"], ["Revision", readResult.identity ? hex(readResult.identity.revision, 8) : "—"], ["SHA-256", readResult.sha256]].map(([label, value]) => <Box key={label}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography className={label === "SHA-256" || label.includes("Code") ? "mono" : ""} noWrap title={value}>{value}</Typography></Box>)}</Box>{!readResult.sii_valid && <Alert severity="warning" sx={{ mt: 1.5 }}>原始 BIN 已完整读取，但 SII 解析失败：{readResult.sii_error}</Alert>}<Accordion disableGutters sx={{ mt: 1.5 }}><AccordionSummary expandIcon={<ExpandMoreRounded />}><Typography fontWeight={700}>Hex View（只读）</Typography></AccordionSummary><AccordionDetails><Box component="pre" className="mono" sx={{ m: 0, p: 1.5, bgcolor: "#F6F8FC", borderRadius: 1, maxHeight: 360, overflow: "auto", fontSize: 12 }}>{formatHexView(readResult.data)}</Box></AccordionDetails></Accordion></CardContent></Card>}
      {operationResult && <Card sx={cardSx}><CardContent><Alert severity={operationResult.severity}><Typography fontWeight={700}>{operationResult.title}</Typography>{operationResult.error ?? operationResult.payload?.result.image_verification}</Alert>{operationResult.payload && <Accordion disableGutters sx={{ mt: 1.2 }}><AccordionSummary expandIcon={<ExpandMoreRounded />}><Typography fontWeight={700}>技术详情</Typography></AccordionSummary><AccordionDetails><Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>{[["写入 Word", operationResult.payload.result.words_written], ["完整回读", `${operationResult.payload.result.bytes_read_back} B`], ["差异字节", operationResult.payload.result.comparison.differing_bytes], ["目标 SHA-256", operationResult.payload.result.comparison.target_sha256], ["回读 SHA-256", operationResult.payload.result.comparison.readback_sha256], ["SII 结构", operationResult.payload.result.sii_valid ? "通过" : "失败"], ["XML 语义", operationResult.payload.result.semantic_valid ? "通过" : "失败"], ["RES 序列", operationResult.payload.result.reset_sequence?.every(Boolean) ? "三帧成功" : "未完成"], ["重新发现", operationResult.payload.result.rediscovered === undefined ? "未执行" : operationResult.payload.result.rediscovered ? "成功" : "失败"], ["重新加载复核", operationResult.payload.result.reload_verified === undefined ? "未执行" : operationResult.payload.result.reload_verified ? "成功" : "失败"]].map(([label, value]) => <Box key={String(label)}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography className={String(label).includes("SHA") ? "mono" : ""} noWrap title={String(value)}>{String(value)}</Typography></Box>)}</Box></AccordionDetails></Accordion>}</CardContent></Card>}
    </Stack>}</>;
}

export default function App() {
  const requestedPage = new URLSearchParams(window.location.search).get("page") as PageKey | null;
  const [page, setPage] = useState<PageKey>(pages.some((item) => item.key === requestedPage) ? requestedPage! : "overview");
  const [status, setStatus] = useState<WorkbenchStatus>({ mode: "real", connected: false, cycle_running: false, slaves: [] });
  const [adapters, setAdapters] = useState<AdapterInfo[]>([]);
  const [adapter, setAdapter] = useState("");
  const [selectedPosition, setSelectedPosition] = useState<number>();
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [busy, setBusy] = useState(false);
  const [autoScanning, setAutoScanning] = useState(true);
  const [message, setMessage] = useState<{ text: string; severity: "success" | "error" | "info" }>();
  const [settings, setSettings] = useState(false);
  const [settingsTab, setSettingsTab] = useState(0);
  const [slaveContextMenu, setSlaveContextMenu] = useState<SlaveContextMenu>();
  const [progress, setProgress] = useState<ProgressState>();
  const slave = status.slaves.find((item) => item.position === selectedPosition);

  const refresh = useCallback(async () => {
    const next = await bridgeRequest<WorkbenchStatus>("status");
    setStatus(next);
    if (next.slaves.length && !next.slaves.some((item) => item.position === selectedPosition)) setSelectedPosition(next.slaves[0].position);
  }, [selectedPosition]);

  const run: Run = useCallback(async (operation, success) => {
    setBusy(true);
    try {
      const result = await operation();
      if (success) setMessage({ text: success, severity: "success" });
      return result;
    } catch (error) {
      const text = error instanceof Error ? error.message : String(error);
      setMessage({ text, severity: "error" });
      setProgress((previous) => previous ? { ...previous, stage: "操作失败", detail: text, tone: "error" } : previous);
      return undefined;
    } finally { setBusy(false); }
  }, []);

  const refreshStates = useCallback(async () => {
    if (!status.connected || !status.slaves.length) {
      await refresh();
      return;
    }
    const slaves = await bridgeRequest<SlaveInfo[]>("read_states");
    setStatus((current) => ({ ...current, slaves }));
    if (slaves.length && !slaves.some((item) => item.position === selectedPosition)) {
      setSelectedPosition(slaves[0].position);
    }
  }, [refresh, selectedPosition, status.connected, status.slaves.length]);

  useEffect(() => {
    const disableBrowserContextMenu = (event: MouseEvent) => event.preventDefault();
    document.addEventListener("contextmenu", disableBrowserContextMenu);
    return () => document.removeEventListener("contextmenu", disableBrowserContextMenu);
  }, []);

  useEffect(() => {
    let active = true;
    let unlisten: (() => void) | undefined;
    setBusy(true);
    const preferredAdapter = window.localStorage.getItem(PREFERRED_ADAPTER_KEY) ?? "";
    bridgeRequest<AutoScanResult>("auto_scan", { preferred_adapter: preferredAdapter })
      .then((result) => {
        if (!active) return;
        setAdapters(result.adapters);
        setAdapter(result.selected_adapter);
        setStatus((current) => ({
          ...current,
          connected: result.connected,
          cycle_running: false,
          slaves: result.slaves,
        }));
        setSelectedPosition(result.slaves[0]?.position);
        if (!result.slaves.length) {
          const failed = result.attempts.filter((attempt) => attempt.error);
          const text = !result.adapters.length
            ? "未发现可用网卡，请检查 Npcap 和网卡状态。"
            : failed.length === result.attempts.length && failed[0]?.error
              ? `自动扫描失败：${failed[0].error}`
              : `已扫描 ${result.attempts.length} 个网卡，未发现 EtherCAT 从站。`;
          setMessage({ text, severity: failed.length === result.attempts.length && failed.length > 0 ? "error" : "info" });
        }
      })
      .catch((error) => {
        if (active) setMessage({ text: error instanceof Error ? error.message : String(error), severity: "error" });
      })
      .finally(() => {
        if (active) { setAutoScanning(false); setBusy(false); }
      });
    onBridgeEvent((event: BridgeEvent) => {
      if (["slaves_changed", "cycle_started", "cycle_stopped"].includes(event.kind)) setStatus((current) => ({ ...current, cycle_running: event.kind === "cycle_started" ? true : event.kind === "cycle_stopped" ? false : current.cycle_running, slaves: event.data as SlaveInfo[] }));
      if (event.kind === "cycle_fault") { setStatus((current) => ({ ...current, cycle_running: false })); setMessage({ text: String(event.data), severity: "error" }); }
      if (event.kind === "process_data") setSnapshot(event.data as Snapshot);
      if (event.kind === "progress") {
        const next = event.data as OperationProgress;
        const fraction = next.total > 0 ? Math.min(1, next.completed / next.total) : 0;
        const ranges: Record<string, [number, number]> = {
          "read-current": [0, 20], "write-verify": [20, 65], "stability-wait": [65, 75],
          "full-verify": [75, 95], reset: [95, 97], "reload-verify": [97, 100],
        };
        const range = ranges[next.stage];
        const calculated = Math.round(range ? range[0] + (range[1] - range[0]) * fraction : fraction * 100);
        const labels: Record<string, string> = {
          read: "完整读取", "backup-read": "读取并保存 BIN", "read-current": "读取当前 EEPROM",
          "write-verify": "写入并校验", "stability-wait": "等待 EEPROM 稳定",
          "full-verify": "完整回读校验", reset: "复位并重新发现", "reload-verify": "复位后重新加载复核",
        };
        setProgress((previous) => {
          if (previous?.percent === 100 && previous.tone !== "info") return previous;
          return { ...next, stage: labels[next.stage] ?? next.stage, percent: Math.max(previous?.percent ?? 0, calculated), tone: "info" };
        });
      }
      if (event.kind === "error") setMessage({ text: event.data instanceof Error ? event.data.message : typeof event.data === "string" ? event.data : JSON.stringify(event.data), severity: "error" });
    }).then((value) => { unlisten = value; });
    return () => { active = false; unlisten?.(); };
  }, []);

  const connect = async () => {
    if (status.connected) await run(() => bridgeRequest("disconnect").then((value) => { setSelectedPosition(undefined); setSnapshot(undefined); return value; }), "已断开网卡");
    else await run(() => bridgeRequest("connect", { adapter }), "网卡已连接");
    await refresh();
  };
  const scan = async () => {
    const found = await run(() => bridgeRequest<SlaveInfo[]>("scan"), "扫描完成");
    if (found) { setStatus((current) => ({ ...current, slaves: found })); setSelectedPosition(found[0]?.position); }
  };
  const switchMode = async (demo: boolean) => {
    const mode = demo ? "demo" : "real";
    const changed = await run(() => bridgeRequest("switch_mode", { mode }), demo ? "已切换到 Demo 模式" : "已切换到实际设备");
    if (changed) {
      setStatus({ mode, connected: false, cycle_running: false, slaves: [] });
      setSelectedPosition(undefined);
      const items = await bridgeRequest<AdapterInfo[]>("enumerate_adapters");
      const preferred = window.localStorage.getItem(PREFERRED_ADAPTER_KEY) ?? "";
      setAdapters(items);
      setAdapter(items.some((item) => item.name === preferred) ? preferred : items[0]?.name ?? "");
    }
  };

  const selectAdapter = (value: string) => {
    setAdapter(value);
    window.localStorage.setItem(PREFERRED_ADAPTER_KEY, value);
  };

  const openSlaveContextMenu = (event: ReactMouseEvent, position: number) => {
    event.preventDefault();
    if (page === "overview") {
      setSelectedPosition(position);
      setSlaveContextMenu({ mouseX: event.clientX + 2, mouseY: event.clientY - 6, position });
    }
  };

  const openSlaveEeprom = () => {
    if (slaveContextMenu) setSelectedPosition(slaveContextMenu.position);
    setSlaveContextMenu(undefined);
    setPage("eeprom");
  };

  const visit = (url: string) => {
    openExternal(url).catch((error) => setMessage({
      text: error instanceof Error ? error.message : String(error),
      severity: "error",
    }));
  };

  const content = useMemo(() => {
    const props = { slave, run };
    if (page === "overview") return <OverviewPage {...props} slaves={status.slaves} refresh={refreshStates} />;
    if (page === "registers") return <RegistersPage {...props} />;
    return <EepromPage {...props} status={status} setProgress={setProgress} />;
  }, [page, slave, status, snapshot, progress, refreshStates, run]);

  return <Box sx={{ display: "flex", height: "100vh", bgcolor: "background.default" }}>
    <Drawer variant="permanent" PaperProps={{ sx: { width: 190, borderRight: 1, borderColor: "divider", bgcolor: "#FBFCFE", overflow: "hidden" } }}>
      <Toolbar sx={{ minHeight: "60px !important", px: "14px !important", gap: 1.2 }}>
        <Box sx={{ width: 34, height: 34, borderRadius: 1.2, bgcolor: "primary.main", color: "white", display: "grid", placeItems: "center", flexShrink: 0 }}><CableRounded fontSize="small" /></Box>
        <Box minWidth={0}><Typography fontWeight={760} lineHeight={1.1}>EtherCAT</Typography><Typography variant="caption" color="text.secondary">Workbench</Typography></Box>
      </Toolbar>
      <Divider />
      <Typography variant="overline" color="text.secondary" sx={{ px: 2, pt: 1.5 }}>工作区</Typography>
      <List sx={{ px: 1, pt: 0.5 }}>{pages.map((item) => <ListItemButton selected={page === item.key} onClick={() => setPage(item.key)} key={item.key} sx={{ minHeight: 44, mb: 0.5, px: 1.3 }}><ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon><ListItemText primary={item.label} primaryTypographyProps={{ fontWeight: 650, fontSize: 14 }} /></ListItemButton>)}</List>
      <Box sx={{ flexGrow: 1 }} />
      <Divider />
      <List sx={{ p: 1 }}><ListItemButton onClick={() => { setSettingsTab(0); setSettings(true); }} sx={{ minHeight: 42, px: 1.3 }}><ListItemIcon sx={{ minWidth: 36 }}><SettingsRounded /></ListItemIcon><ListItemText primary="设置" primaryTypographyProps={{ fontWeight: 650, fontSize: 14 }} /></ListItemButton></List>
    </Drawer>
    <Box sx={{ ml: "190px", flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
      <AppBar position="static" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: "divider", bgcolor: "rgba(255,255,255,.96)" }}>
        <Toolbar sx={{ minHeight: "60px !important", gap: 1, px: "18px !important" }}>
          <Stack sx={{ mr: "auto", minWidth: 170 }} spacing={0.15}>
            <Stack direction="row" gap={0.8} alignItems="center">
              <Chip size="small" color={autoScanning ? "primary" : status.connected ? "success" : "default"} variant={status.connected ? "filled" : "outlined"} label={autoScanning ? "正在自动扫描" : status.connected ? "已连接" : "未连接"} />
              {status.mode === "demo" && <Chip size="small" color="warning" label="Demo" />}
              {previewMode && <Chip size="small" variant="outlined" label="预览" />}
            </Stack>
            <Typography variant="caption" color="text.secondary">{autoScanning ? "正在按优先级检查所有网卡…" : status.connected ? `已发现 ${status.slaves.length} 个从站` : "可手动选择网卡后连接"}</Typography>
          </Stack>
          <FormControl size="small" sx={{ width: { xs: 270, xl: 330 } }}><InputLabel>网卡</InputLabel><Select label="网卡" value={adapter} disabled={status.connected || autoScanning} onChange={(e) => selectAdapter(e.target.value)}>{adapters.map((item) => <MenuItem value={item.name} key={item.name}>{item.description || item.name}</MenuItem>)}</Select></FormControl>
          <Button size="small" variant={status.connected ? "outlined" : "contained"} color={status.connected ? "error" : "primary"} startIcon={<UsbRounded />} disabled={autoScanning || busy || (!status.connected && !adapter)} onClick={connect}>{status.connected ? "断开" : "连接"}</Button>
          <Button size="small" variant="outlined" startIcon={<RefreshRounded />} disabled={autoScanning || busy || !status.connected || status.cycle_running} onClick={scan}>扫描</Button>
          {busy && <CircularProgress size={20} sx={{ ml: 0.5 }} />}
        </Toolbar>
      </AppBar>
      <Box sx={{ display: "flex", minHeight: 0, flex: 1 }}>
        {status.slaves.length > 0 && <Box component="aside" sx={{ width: { xs: 228, xl: 246 }, flexShrink: 0, bgcolor: "background.paper", borderRight: 1, borderColor: "divider", overflow: "auto", p: 1 }}><Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ px: 1, py: 0.7 }}><Typography variant="overline" color="text.secondary">从站 · {status.slaves.length}</Typography><Chip size="small" variant="outlined" label={status.cycle_running ? "周期运行" : "周期停止"} /></Stack><List dense sx={{ pt: 0.5 }}>{status.slaves.map((item) => <ListItemButton key={item.position} selected={item.position === selectedPosition} onClick={() => setSelectedPosition(item.position)} onContextMenu={(event) => openSlaveContextMenu(event, item.position)} sx={{ mb: 0.4, py: 0.8, px: 1 }}><ListItemIcon sx={{ minWidth: 34 }}><DeveloperBoardRounded fontSize="small" color={item.state === 8 ? "success" : "action"} /></ListItemIcon><ListItemText primary={`${item.position}. ${item.name}`} secondary={`${stateLabel(item.state)} · ${item.input_size}/${item.output_size} B · ${item.chip_model}`} primaryTypographyProps={{ noWrap: true, fontWeight: 650, fontSize: 13.5 }} secondaryTypographyProps={{ noWrap: true, fontSize: 12 }} /></ListItemButton>)}</List></Box>}
        <Box component="main" sx={{ flex: 1, minWidth: 0, overflow: "auto", p: { xs: 2, xl: 2.5 } }}><Box sx={{ width: "100%", maxWidth: 1760, mx: "auto" }}>{content}</Box></Box>
      </Box>
    </Box>
    <Menu
      open={Boolean(slaveContextMenu)}
      onClose={() => setSlaveContextMenu(undefined)}
      anchorReference="anchorPosition"
      anchorPosition={slaveContextMenu ? { top: slaveContextMenu.mouseY, left: slaveContextMenu.mouseX } : undefined}
      slotProps={{ paper: { sx: { minWidth: 210, border: 1, borderColor: "divider", boxShadow: "0 10px 30px rgba(23,32,51,.16)" } } }}
    >
      <MenuItem onClick={openSlaveEeprom}>
        <ListItemIcon><MemoryRounded fontSize="small" color="warning" /></ListItemIcon>
        <ListItemText primary="烧录 EEPROM" secondary={slaveContextMenu ? `从站 ${slaveContextMenu.position} · 打开烧录页面` : ""} />
      </MenuItem>
    </Menu>
    <Dialog open={settings} onClose={() => setSettings(false)} fullWidth maxWidth="sm">
      <DialogTitle sx={{ pb: 1 }}>设置</DialogTitle>
      <Tabs value={settingsTab} onChange={(_, value) => setSettingsTab(value)} sx={{ px: 2.5, minHeight: 42 }}>
        <Tab icon={<SettingsRounded fontSize="small" />} iconPosition="start" label="通用" sx={{ minHeight: 42 }} />
        <Tab icon={<InfoOutlineRounded fontSize="small" />} iconPosition="start" label="关于" sx={{ minHeight: 42 }} />
      </Tabs>
      <Divider />
      <DialogContent sx={{ minHeight: 360 }}>
        {settingsTab === 0 ? <Stack spacing={2} sx={{ pt: 0.5 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", p: 2, border: 1, borderColor: "divider", borderRadius: 1.25 }}>
            <Box><Typography fontWeight={700}>Demo 模式</Typography><Typography variant="body2" color="text.secondary">使用模拟从站，不访问实际 EtherCAT 网卡。</Typography></Box>
            <Switch checked={status.mode === "demo"} disabled={status.connected} onChange={(e) => switchMode(e.target.checked)} />
          </Box>
          {status.connected && <Alert severity="info">切换模式前请停止周期通信并断开网卡。</Alert>}
        </Stack> : <Stack spacing={2} sx={{ pt: 0.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 2, border: 1, borderColor: "divider", borderRadius: 1.25, bgcolor: "#F8FAFF" }}>
            <Box sx={{ width: 52, height: 52, borderRadius: 1.5, bgcolor: "primary.main", color: "white", display: "grid", placeItems: "center", flexShrink: 0 }}><CableRounded /></Box>
            <Box sx={{ minWidth: 0, flex: 1 }}><Stack direction="row" alignItems="center" gap={1}><Typography variant="h6">EtherCAT Workbench</Typography><Chip size="small" variant="outlined" label={`v${packageInfo.version}`} /></Stack><Typography variant="body2" color="text.secondary">面向 Windows 的 EtherCAT 从站调试与诊断工作台</Typography></Box>
          </Box>
          <Typography variant="body2" color="text.secondary">聚焦从站概览、ESC 标准寄存器诊断与 EEPROM 安全读取、备份、烧录和恢复。硬件通信由独立 Python Bridge 与 Worker 串行执行。</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1.2 }}>
            {[["版本", packageInfo.version], ["通信核心", "pySOEM 1.1.13"], ["许可证", "PolyForm NC 1.0"]].map(([label, value]) => <Box key={label} sx={{ p: 1.4, border: 1, borderColor: "divider", borderRadius: 1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" fontWeight={700} sx={{ mt: 0.3 }}>{value}</Typography></Box>)}
          </Box>
          <Divider />
          <Stack direction="row" gap={1} flexWrap="wrap">
            <Button variant="contained" startIcon={<GitHubIcon />} endIcon={<OpenInNewRounded fontSize="small" />} onClick={() => visit(PROJECT_URL)}>GitHub 项目</Button>
            <Button variant="outlined" startIcon={<BugReportRounded />} endIcon={<OpenInNewRounded fontSize="small" />} onClick={() => visit(ISSUES_URL)}>问题反馈</Button>
          </Stack>
          <Typography variant="caption" color="text.secondary">Copyright © EtherCAT Workbench contributors</Typography>
        </Stack>}
      </DialogContent>
      <DialogActions><Button onClick={() => setSettings(false)}>完成</Button></DialogActions>
    </Dialog>
    <Snackbar open={Boolean(progress)} autoHideDuration={progress?.percent === 100 ? 6000 : null} onClose={(_, reason) => { if (reason !== "clickaway" && progress?.percent === 100) setProgress(undefined); }} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
      <Alert severity={progress?.tone === "error" ? "error" : progress?.tone === "success" ? "success" : "info"} variant="filled" action={progress && progress.percent < 100 ? <Button color="inherit" size="small" onClick={() => bridgeRequest("cancel")}>取消</Button> : undefined} sx={{ width: 440, alignItems: "center" }}>
        <Typography fontWeight={750}>{progress?.stage}</Typography><Typography variant="body2">{progress?.detail}</Typography>{progress && <LinearProgress color="inherit" variant="determinate" value={progress.percent} sx={{ mt: 1, height: 5, borderRadius: 8, bgcolor: "rgba(255,255,255,.25)" }} />}
      </Alert>
    </Snackbar>
    <Snackbar open={Boolean(message)} autoHideDuration={5000} onClose={() => setMessage(undefined)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}><Alert severity={message?.severity} variant="filled" onClose={() => setMessage(undefined)}>{message?.text}</Alert></Snackbar>
  </Box>;
}
