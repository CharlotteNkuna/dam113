//@ts-check
'use strict';
const path = require('path');
const CopyPlugin = require('copy-webpack-plugin');

const jbStatic = path.resolve(__dirname, '../jetbrains-thunder-client/src/main/resources/static');

/** @type {import('webpack').Configuration} */
module.exports = {
    name: 'jetbrains-sync',
    mode: 'none',
    entry: {},
    output: {
        path: path.resolve(__dirname, 'dist'),
    },
    plugins: [
        new CopyPlugin({
            patterns: [
                { from: "dist/main.bundle.js",                  to: `${jbStatic}/js/tc-chunk-1.js`,  noErrorOnMissing: true },
                { from: "out/jsbundles/request.init.js",        to: `${jbStatic}/js/tc-chunk-2.js`,  noErrorOnMissing: true },
                { from: "out/jsbundles/sidebar.bundle.js",      to: `${jbStatic}/js/tc-chunk-3.js`,  noErrorOnMissing: true },
                { from: "dist/chunk1.js",                       to: `${jbStatic}/js/tc-chunk-4.js`,  noErrorOnMissing: true },
                { from: "out/jsbundles/col-settings.inline.js", to: `${jbStatic}/js/tc-chunk-5.js`,  noErrorOnMissing: true },
                { from: "out/jsbundles/environment.bundle.js",  to: `${jbStatic}/js/tc-chunk-6.js`,  noErrorOnMissing: true },
                { from: "out/jsbundles/addToCollection.bundle.js", to: `${jbStatic}/js/tc-chunk-7.js`, noErrorOnMissing: true },
                { from: "out/jsbundles/manage-account.bundle.js",  to: `${jbStatic}/js/tc-chunk-8.js`, noErrorOnMissing: true },
                { from: "out/jsbundles/manage-cookies.bundle.js",  to: `${jbStatic}/js/tc-chunk-9.js`, noErrorOnMissing: true },
                { from: "dist/main.min.css",                    to: `${jbStatic}/css/tc-bundle-1.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/request.inline.css",    to: `${jbStatic}/css/tc-bundle-2.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/sidebar.min.css",       to: `${jbStatic}/css/tc-bundle-3.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/colSettings.min.css",   to: `${jbStatic}/css/tc-bundle-4.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/environment.min.css",   to: `${jbStatic}/css/tc-bundle-5.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/addToCollection.min.css", to: `${jbStatic}/css/tc-bundle-6.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/manage-account.min.css",  to: `${jbStatic}/css/tc-bundle-7.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/manage-cookies.min.css",  to: `${jbStatic}/css/tc-bundle-8.css`, noErrorOnMissing: true },
                { from: "out/cssbundles/markdownView.min.css",    to: `${jbStatic}/css/tc-bundle-9.css`, noErrorOnMissing: true },
            ],
        }),
    ],
};
