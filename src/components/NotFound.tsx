const NotFound = () => (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="text-center">
            <h1 className="text-4xl font-bold mb-4">404</h1>
            <p className="text-xl text-gray-600 mb-4">Упс! Страница не найдена</p>
            <a href="/" className="text-blue-500 hover:text-blue-700 underline">
                Вернуться на главную
            </a>
        </div>
    </div>
);

export default NotFound;
