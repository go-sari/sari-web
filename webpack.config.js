const path = require('path');
const glob = require('glob')

const {CleanWebpackPlugin} = require('clean-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const ImageminPlugin = require('imagemin-webpack-plugin').default;

module.exports = {
    mode: "development",
    entry: {
        db_config: "./src/db_config/app.js",
        select_account: "./src/select_account/app.js",
    },
    plugins: [
        new CleanWebpackPlugin(),
        new MiniCssExtractPlugin({
            filename: 'css/[name].css',
            chunkFilename: 'css/[id].css',
        }),
        new ImageminPlugin({
            externalImages: {
                context: 'src',
                sources: glob.sync('src/images/*.{png,ico}'),
                destination: 'dist',
                fileName: '[path][name].[ext]'
            }
        }),
    ],
    externals: {
        axios: 'axios',
        bootbox: 'bootbox',
        clipboard: 'ClipboardJS',
        jquery: 'jQuery',
        moment: 'moment',
        'popper.js': 'popper',
        bootstrap: 'bootstrap',
        'bootstrap-select': 'bootstrap-select',
    },
    output: {
        path: path.resolve(__dirname, 'dist'),
        filename: 'js/[name].bundle.js',
    },
    module: {
        rules: [
            {
                test: /\.js$/,
                exclude: /(node_modules)/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: ['@babel/preset-env'],
                    },
                },
            },
            {
                test: require.resolve('jquery'),
                loader: 'expose-loader',
                options: {
                    exposes: ['$', 'jQuery'],
                },
            },
            {
                test: /\.css$/,
                use: [
                    {
                        loader: MiniCssExtractPlugin.loader,
                        options: {
                            hmr: process.env.NODE_ENV === 'development',
                        },
                    },
                    'css-loader',
                ],
            }
        ],
    },
};
