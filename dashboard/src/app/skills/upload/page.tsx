"use client";

import { useState } from "react";
import {
  Upload,
  Shield,
  AlertTriangle,
  Check,
  Loader2,
  FileUp,
  X,
  Info,
  ArrowLeft,
} from "lucide-react";
import Link from "next/link";

export default function SkillsUploadPage() {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [author, setAuthor] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [baseModel, setBaseModel] = useState("Qwen/Qwen2.5-Coder-7B-Instruct");
  const [framework, setFramework] = useState("");
  const [industry, setIndustry] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{
    success: boolean;
    message: string;
    adapter_id?: string;
    file_name?: string;
    file_size_mb?: number;
    scan?: {
      passed: boolean;
      score: number;
      total_issues: number;
      pii_found?: string[];
      proprietary_found?: string[];
    };
  } | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !name) return;

    setUploading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("name", name);
      formData.append("description", description);
      formData.append("author", author || "anonymous");
      formData.append("version", version);
      formData.append("base_model", baseModel);
      formData.append("framework", framework);
      formData.append("industry", industry);
      if (tags) formData.append("tags", tags);

      const res = await fetch("http://localhost:7337/api/marketplace/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      setResult(data);
    } catch (e) {
      setResult({ success: false, message: "Upload failed: Network error" });
    } finally {
      setUploading(false);
    }
  }

  function handleFileDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.name.endsWith(".zip") || droppedFile.name.endsWith(".safetensors") || droppedFile.name.endsWith(".bin"))) {
      setFile(droppedFile);
    }
  }

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          href="/skills"
          className="btn-ghost p-2 text-text-muted hover:text-text-primary"
        >
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-3">
            <Upload className="w-7 h-7 text-forge-primary" />
            Upload Adapter
          </h1>
          <p className="text-text-muted mt-1">
            Share your fine-tuned adapter with the community
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* File Upload */}
        <div className="card p-6">
          <label className="block text-sm font-medium text-text-primary mb-2">
            Adapter File *
          </label>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleFileDrop}
            className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${
              dragOver
                ? "border-forge-primary bg-forge-primary/5"
                : file
                  ? "border-success bg-success/5"
                  : "border-forge-border hover:border-forge-primary/50"
            }`}
          >
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <FileUp size={24} className="text-success" />
                <div className="text-left">
                  <p className="text-sm font-medium text-text-primary">{file.name}</p>
                  <p className="text-xs text-text-muted">
                    {(file.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setFile(null)}
                  className="btn-ghost p-1 text-text-muted hover:text-error ml-4"
                >
                  <X size={16} />
                </button>
              </div>
            ) : (
              <div>
                <FileUp size={32} className="mx-auto text-text-muted mb-3" />
                <p className="text-text-muted mb-1">
                  Drop your adapter file here, or{" "}
                  <label className="text-forge-primary hover:underline cursor-pointer">
                    browse
                    <input
                      type="file"
                      accept=".zip,.safetensors,.bin,.pt"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                      className="hidden"
                    />
                  </label>
                </p>
                <p className="text-xs text-text-muted">
                  Supports .zip, .safetensors, .bin, .pt (max 500 MB)
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Metadata */}
        <div className="card p-6 space-y-4">
          <h3 className="font-semibold text-text-primary flex items-center gap-2">
            <Info size={16} className="text-forge-primary" />
            Adapter Metadata
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Name *
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Python Coder v1"
                className="input w-full"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Author
              </label>
              <input
                type="text"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="Your name / handle"
                className="input w-full"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-primary mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what your adapter does, what it's fine-tuned for..."
              className="input w-full h-24 resize-none"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Version
              </label>
              <input
                type="text"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                className="input w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Base Model
              </label>
              <input
                type="text"
                value={baseModel}
                onChange={(e) => setBaseModel(e.target.value)}
                className="input w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Framework
              </label>
              <select
                value={framework}
                onChange={(e) => setFramework(e.target.value)}
                className="input w-full"
              >
                <option value="">Select...</option>
                <option value="pytorch">PyTorch</option>
                <option value="tensorflow">TensorFlow</option>
                <option value="jax">JAX</option>
                <option value="onnx">ONNX</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Industry
              </label>
              <select
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                className="input w-full"
              >
                <option value="">General</option>
                <option value="web">Web</option>
                <option value="backend">Backend</option>
                <option value="data">Data</option>
                <option value="systems">Systems</option>
                <option value="mobile">Mobile</option>
                <option value="devops">DevOps</option>
                <option value="security">Security</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-primary mb-1">
                Tags (comma separated)
              </label>
              <input
                type="text"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="python, code-gen, qwen"
                className="input w-full"
              />
            </div>
          </div>
        </div>

        {/* Sanitization Notice */}
        <div className="card p-4 border-amber-500/30 bg-amber-500/5">
          <div className="flex items-start gap-3">
            <Shield size={20} className="text-warning shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-text-primary">Automated Security Scan</p>
              <p className="text-xs text-text-muted mt-1">
                Uploaded adapters are automatically scanned for PII, API keys, and proprietary code.
                Adapters with issues may be rejected or flagged as unverified.
              </p>
            </div>
          </div>
        </div>

        {/* Result */}
        {result && (
          <div
            className={`card p-4 ${
              result.success
                ? "border-success/30 bg-success/5"
                : "border-error/30 bg-error/5"
            }`}
          >
            {result.success ? (
              <div className="flex items-start gap-3">
                <Check size={20} className="text-success shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-success">Upload Successful!</p>
                  <p className="text-xs text-text-muted mt-0.5">{result.message}</p>
                  {result.file_name && (
                    <p className="text-xs text-text-muted mt-1">
                      File: {result.file_name} ({result.file_size_mb} MB)
                    </p>
                  )}
                  {result.adapter_id && (
                    <p className="text-xs text-text-muted">
                      ID: <code className="text-forge-primary">{result.adapter_id}</code>
                    </p>
                  )}
                  {result.scan && (
                    <div className="mt-2 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium">Sanitization:</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          result.scan.passed
                            ? "bg-success/10 text-success"
                            : "bg-warning/10 text-warning"
                        }`}>
                          Score {result.scan.score}/1.0
                        </span>
                      </div>
                      {result.scan.pii_found && result.scan.pii_found.length > 0 && (
                        <div>
                          <p className="text-xs text-warning mt-1">⚠️ {result.scan.pii_found.length} PII patterns detected:</p>
                          <ul className="text-xs text-text-muted mt-0.5 space-y-0.5">
                            {result.scan.pii_found.slice(0, 3).map((item, i) => (
                              <li key={i} className="truncate">- {item}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {result.scan.proprietary_found && result.scan.proprietary_found.length > 0 && (
                        <p className="text-xs text-warning">
                          ⚠️ {result.scan.proprietary_found.length} proprietary markers detected
                        </p>
                      )}
                      {result.scan.passed && result.scan.score >= 0.9 && (
                        <p className="text-xs text-success mt-1">✅ No sensitive content detected</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="text-error shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-error">Upload Failed</p>
                  <p className="text-xs text-text-muted">{result.message}</p>
                  {result.scan && !result.scan.passed && (
                    <div className="mt-2 space-y-1">
                      <p className="text-xs text-warning">
                        ⚠️ Sanitization score: {result.scan.score}/1.0 ({result.scan.total_issues} issues)
                      </p>
                      {result.scan.pii_found && result.scan.pii_found.length > 0 && (
                        <div>
                          <p className="text-xs text-warning mt-1">PII detected:</p>
                          <ul className="text-xs text-text-muted mt-0.5 space-y-0.5">
                            {result.scan.pii_found.slice(0, 3).map((item, i) => (
                              <li key={i} className="truncate">- {item}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Submit */}
        <div className="flex justify-end gap-3">
          <Link href="/skills" className="btn-ghost px-4 py-2 text-sm">
            Cancel
          </Link>
          <button
            type="submit"
            disabled={!file || !name || uploading}
            className="btn-primary px-6 py-2 text-sm flex items-center gap-2"
          >
            {uploading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Scanning & Uploading...
              </>
            ) : (
              <>
                <Upload size={16} />
                Upload Adapter
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
