using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;

public static class LocalAgentSetupStub
{
    private static readonly byte[] Marker = System.Text.Encoding.ASCII.GetBytes("LOCAL_AGENT_ZIP_PAYLOAD_V1\n");

    public static int Main()
    {
        string exePath = Process.GetCurrentProcess().MainModule.FileName;
        string tempRoot = Path.Combine(Path.GetTempPath(), "LocalAgentSetup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            string zipPath = Path.Combine(tempRoot, "LocalAgent.zip");
            ExtractPayload(exePath, zipPath);
            ZipFile.ExtractToDirectory(zipPath, tempRoot);

            string installScript = Path.Combine(tempRoot, "install-local-agent.ps1");
            if (!File.Exists(installScript))
            {
                throw new FileNotFoundException("install-local-agent.ps1 not found inside payload.", installScript);
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + installScript + "\"",
                UseShellExecute = false,
            };

            using (var process = Process.Start(startInfo))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
        finally
        {
            try
            {
                if (Directory.Exists(tempRoot))
                {
                    Directory.Delete(tempRoot, true);
                }
            }
            catch
            {
            }
        }
    }

    private static void ExtractPayload(string exePath, string zipPath)
    {
        byte[] bytes = File.ReadAllBytes(exePath);
        int markerOffset = LastIndexOf(bytes, Marker);
        if (markerOffset < 0)
        {
            throw new InvalidOperationException("Installer payload marker was not found.");
        }

        int payloadOffset = markerOffset + Marker.Length;
        using (var output = File.Create(zipPath))
        {
            output.Write(bytes, payloadOffset, bytes.Length - payloadOffset);
        }
    }

    private static int LastIndexOf(byte[] haystack, byte[] needle)
    {
        for (int i = haystack.Length - needle.Length; i >= 0; i--)
        {
            bool matched = true;
            for (int j = 0; j < needle.Length; j++)
            {
                if (haystack[i + j] != needle[j])
                {
                    matched = false;
                    break;
                }
            }
            if (matched)
            {
                return i;
            }
        }
        return -1;
    }
}
