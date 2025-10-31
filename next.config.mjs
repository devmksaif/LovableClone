/** @type {import('next').NextConfig} */
const nextConfig = {
  webpack: (config, { isServer }) => {
    // Handle ONNX runtime binaries
    config.resolve.alias = {
      ...config.resolve.alias,
      'onnxruntime-node': false,
    };

    // Exclude ONNX runtime from client-side bundles
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        'onnxruntime-node': false,
        fs: false,
        path: false,
      };
    }

    return config;
  },
};

export default nextConfig;