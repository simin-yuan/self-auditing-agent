package com.demo;

import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.PostMapping;

/**
 * 故意违规的替身：这个文件里的入口与下表【完全没有登记】到
 * source-asset-inventory.md —— 用于证明「源码对账」规则真的会开火。
 */
@RestController
@RequestMapping("/api/order")
public class OrderController {

    @PostMapping("/create")
    public Object create(Object req) {
        return null;
    }
}
