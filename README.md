# EC2 Mobile Control PWA

A mobile-first Progressive Web App (PWA) built with pure Vanilla HTML, CSS, and JavaScript (zero build tools required) to securely start, stop, monitor, and track costs for an AWS EC2 Windows development server.

## Project Structure

```text
ec2-control-pwa/
├── frontend/
│   ├── index.html               # Complete single-file PWA UI + logic
│   ├── manifest.webmanifest     # Web App Manifest for Add to Home Screen
│   ├── sw.js                    # Service Worker for app-shell caching
│   └── icons/
│       ├── icon-192.svg
│       └── icon-512.svg
├── backend/
│   ├── lambda_function.py       # Python 3.12 AWS Lambda handler
│   └── iam-policy.json          # Least-privilege IAM policy for Lambda
└── README.md
```

## Quick Deployment Guide

1. **IAM Role**: Create an IAM Role for Lambda and attach `backend/iam-policy.json` (replace `<REGION>`, `<ACCOUNT_ID>`, and `<INSTANCE_ID>`).
2. **AWS Lambda**: Create a Python 3.12 Lambda function using `backend/lambda_function.py`. Set environment variables:
   - `ALLOWED_INSTANCE_IDS`: `i-0abc123456789def0`
   - `ALLOWED_ORIGIN`: `https://your-pwa-domain.com`
   - `DEFAULT_HOURLY_RATE`: `0.19`
3. **API Gateway**: Create a REST API with Lambda Proxy Integration for:
   - `GET /status`
   - `POST /start`
   - `POST /stop`
   - `GET /cost`
   Enable CORS and require an API Key (`x-api-key`) on each method.
4. **Static Hosting (HTTPS)**: Upload the contents of `frontend/` to AWS S3 + CloudFront, GitHub Pages, or Netlify.
5. **Install on Mobile**: Open the HTTPS URL on Safari (iOS) or Chrome (Android), configure your Region, Instance ID, API URL, and API Key in **Settings**, and select **Add to Home Screen**.
