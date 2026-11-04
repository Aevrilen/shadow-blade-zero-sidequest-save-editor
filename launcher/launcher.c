/* Native GUI entry point. No CRT, shell, installed Python or PATH lookup.
 * Only the explicitly created desktop process joins our job. Any processes
 * it explicitly opens (e.g. a backup folder) silently break away.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

#define CAPACITY 32768
static WCHAR root[CAPACITY], runtime_path[CAPACITY], script_path[CAPACITY];
static WCHAR command_line[CAPACITY], error_text[4096];
static CHAR error_utf8[16384];
static HANDLE volatile service_job;
static STARTUPINFOW startup;
static PROCESS_INFORMATION child;
static JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits;

static BOOL append(WCHAR *target, DWORD capacity, const WCHAR *text) {
    DWORD offset = 0, i = 0;
    while (offset < capacity && target[offset]) ++offset;
    if (offset == capacity) return FALSE;
    while (text[i]) {
        if (offset + 1 >= capacity) return FALSE;
        target[offset++] = text[i++];
    }
    target[offset] = 0;
    return TRUE;
}

static BOOL add_character(WCHAR value) {
    WCHAR text[2];
    text[0] = value; text[1] = 0;
    return append(command_line, CAPACITY, text);
}

/* Microsoft command-line escaping: quotes and trailing backslashes round-trip. */
static BOOL argument(const WCHAR *text) {
    DWORD i = 0, slashes, count;
    if (!add_character(L'"')) return FALSE;
    while (text[i]) {
        slashes = 0;
        while (text[i] == L'\\') { ++slashes; ++i; }
        count = slashes;
        if (!text[i] || text[i] == L'"') count *= 2;
        if (text[i] == L'"') ++count;
        while (count--) if (!add_character(L'\\')) return FALSE;
        if (text[i] && !add_character(text[i++])) return FALSE;
    }
    return add_character(L'"');
}

static void release_job(void) {
    HANDLE handle = (HANDLE)InterlockedExchangePointer((PVOID volatile *)&service_job, NULL);
    if (handle) CloseHandle(handle);
}

static void fail(const WCHAR *message, DWORD code) {
    WCHAR *system_message = NULL;
    DWORD length = 0, written;
    HANDLE output = GetStdHandle(STD_ERROR_HANDLE);
    error_text[0] = 0;
    append(error_text, 4096, message);
    if (code && FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                              FORMAT_MESSAGE_IGNORE_INSERTS, NULL, code, 0,
                              (WCHAR *)&system_message, 0, NULL)) {
        append(error_text, 4096, L"\r\n\r\n");
        append(error_text, 4096, system_message);
        LocalFree(system_message);
    }
    append(error_text, 4096, L"\r\n");
    while (error_text[length]) ++length;
    if (output && output != INVALID_HANDLE_VALUE && !WriteConsoleW(output, error_text, length, &written, NULL)) {
        int size = WideCharToMultiByte(CP_UTF8, 0, error_text, (int)length,
                                       error_utf8, sizeof(error_utf8), NULL, NULL);
        if (size > 0) WriteFile(output, error_utf8, (DWORD)size, &written, NULL);
    }
    MessageBoxW(NULL, error_text, L"影之刃零支线存档修改器", MB_OK | MB_ICONERROR);
    release_job();
    ExitProcess(code ? code : 1);
}

void launcher_entry(void) {
    DWORD size, last_slash = 0, attributes, exit_code = 1;
    int count, i;
    WCHAR **arguments;
    BOOL drive_root;

    size = GetModuleFileNameW(NULL, root, CAPACITY);
    if (!size || size >= CAPACITY - 1) fail(L"无法定位程序目录。请完整解压后再启动。", GetLastError());
    for (i = 0; root[i]; ++i) if (root[i] == L'\\' || root[i] == L'/') last_slash = (DWORD)i;
    if (!last_slash) fail(L"无法定位程序目录。请完整解压后再启动。", 0);
    drive_root = last_slash == 2 && root[1] == L':';
    root[last_slash + (drive_root ? 1 : 0)] = 0;
    if (!append(runtime_path, CAPACITY, root) || !append(runtime_path, CAPACITY, drive_root ? L"" : L"\\") ||
        !append(runtime_path, CAPACITY, L"runtime\\pythonw.exe") ||
        !append(script_path, CAPACITY, root) || !append(script_path, CAPACITY, drive_root ? L"" : L"\\") ||
        !append(script_path, CAPACITY, L"launcher.py"))
        fail(L"程序所在路径过长，请解压到较短的目录后重试。", 0);
    attributes = GetFileAttributesW(runtime_path);
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY))
        fail(L"随包运行环境缺失。请完整解压 ZIP，保留 runtime 文件夹后重试。", 0);
    attributes = GetFileAttributesW(script_path);
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY))
        fail(L"程序源码缺失。请完整解压 ZIP，保留 launcher.py 后重试。", 0);

    arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!arguments) fail(L"无法读取启动参数。", GetLastError());
    if (!argument(runtime_path) || !append(command_line, CAPACITY, L" -I -B -X utf8 ") || !argument(script_path))
        fail(L"程序所在路径或启动参数过长。", 0);
    for (i = 1; i < count; ++i)
        if (!add_character(L' ') || !argument(arguments[i])) fail(L"启动参数过长。", 0);
    LocalFree(arguments);

    service_job = CreateJobObjectW(NULL, NULL);
    if (!service_job) fail(L"无法建立桌面程序的退出关联。", GetLastError());
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK;
    if (!SetInformationJobObject(service_job, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
        fail(L"无法配置桌面程序的退出关联。", GetLastError());
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    if (!CreateProcessW(runtime_path, command_line, NULL, NULL, TRUE, CREATE_SUSPENDED,
                        NULL, root, &startup, &child))
        fail(L"无法启动随包运行环境。请完整解压到可运行的本地目录后重试。", GetLastError());
    if (!AssignProcessToJobObject(service_job, child.hProcess)) {
        DWORD error = GetLastError();
        TerminateProcess(child.hProcess, error);
        CloseHandle(child.hThread); CloseHandle(child.hProcess);
        fail(L"无法建立桌面程序的退出关联；程序尚未启动。", error);
    }
    if (ResumeThread(child.hThread) == (DWORD)-1) {
        DWORD error = GetLastError();
        CloseHandle(child.hThread); CloseHandle(child.hProcess);
        fail(L"无法启动桌面程序。", error);
    }
    CloseHandle(child.hThread);
    WaitForSingleObject(child.hProcess, INFINITE);
    GetExitCodeProcess(child.hProcess, &exit_code);
    CloseHandle(child.hProcess);
    release_job();
    if (exit_code) fail(L"修改器未能正常启动或已异常退出。运行环境可能缺失，请重新完整解压后重试。", exit_code);
    ExitProcess(exit_code);
}
