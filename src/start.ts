import {createStart} from "@tanstack/react-start";
import {buildIdFetch} from "@/platform/build-id";

export const startInstance = createStart(() => ({
    serverFns: {fetch: buildIdFetch},
}));
